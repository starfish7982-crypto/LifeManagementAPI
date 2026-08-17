"""Telegram Bot API client.

Notes on the choices here, which are the interesting part in an interview:

  * Failures are swallowed and reported, never raised. A notification that cannot be
    delivered must not turn a successful API write into a 500 for the caller.
  * Retries apply only to timeouts and 5xx. Retrying a 400 ("chat not found") would
    just burn the rate limit three times before failing anyway.
  * The bot token never appears in a log line or an error message.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_ATTEMPTS = 3


class TelegramClient:
    """Posts to one chat.

    Takes the credentials rather than the application Settings, because they are now a
    per-user value in the database. A client reading global configuration could only
    notify one chat for the whole service.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings, client: httpx.AsyncClient | None = None):
        """Build from the environment. Used as a fallback when a user has set nothing."""
        return cls(settings.telegram_bot_token, settings.telegram_chat_id, client=client)

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    async def send_message(self, text: str) -> bool:
        """Send `text`. Returns True on delivery, False on any failure."""
        if not self.enabled:
            log.info("Telegram disabled; skipping notification")
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code < 300:
                        return True
                    if resp.status_code < 500:
                        # Client error: the request itself is wrong. Retrying is pointless.
                        log.warning("Telegram rejected the message (%s)", resp.status_code)
                        return False
                    log.warning(
                        "Telegram server error %s (attempt %s/%s)",
                        resp.status_code,
                        attempt,
                        _MAX_ATTEMPTS,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    log.warning(
                        "Telegram transport failure: %s (attempt %s/%s)",
                        type(exc).__name__,
                        attempt,
                        _MAX_ATTEMPTS,
                    )
                if attempt < _MAX_ATTEMPTS:
                    await asyncio.sleep(2 ** (attempt - 1))  # 1s, then 2s
            return False
        finally:
            if owns_client:
                await client.aclose()
