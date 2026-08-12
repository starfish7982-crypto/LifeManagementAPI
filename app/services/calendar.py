"""Google Calendar integration over the secret iCal (.ics) URL.

Why iCal rather than the Google Calendar API: the API needs an OAuth consent screen,
a refresh-token store, and a Google Cloud project. The secret .ics URL is a single
read-only string, which is the right amount of machinery for reading one personal
calendar. The trade-off is stated so the choice is visibly deliberate, not lazy.

The feed is cached in memory with a TTL. Google rate-limits these URLs, and a
dashboard that refreshes on every page load would otherwise hit them constantly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from icalendar import Calendar

from app.config import Settings
from app.schemas import CalendarEvent

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass
class _CacheEntry:
    fetched_at: float
    events: list[CalendarEvent]


class CalendarClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._cache: _CacheEntry | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.calendar_enabled

    def _cache_is_fresh(self) -> bool:
        if self._cache is None:
            return False
        age = time.monotonic() - self._cache.fetched_at
        return age < self._settings.calendar_cache_ttl_seconds

    async def events_on(self, day: date, *, force_refresh: bool = False) -> list[CalendarEvent]:
        """Events occurring on `day`. Returns [] if the calendar is unreachable."""
        if not self.enabled:
            return []

        if force_refresh or not self._cache_is_fresh():
            fetched = await self._fetch()
            if fetched is None:
                # Serve stale data rather than nothing: a calendar outage should degrade
                # the response, not empty it.
                if self._cache is not None:
                    log.warning("Calendar fetch failed; serving stale cache")
                    return [e for e in self._cache.events if e.starts_at == day]
                return []
            self._cache = _CacheEntry(fetched_at=time.monotonic(), events=fetched)

        assert self._cache is not None
        return [e for e in self._cache.events if e.starts_at == day]

    async def _fetch(self) -> list[CalendarEvent] | None:
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        owns_client = self._client is None
        try:
            resp = await client.get(self._settings.google_calendar_ical_url)
            resp.raise_for_status()
            return parse_ical(resp.content)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Calendar fetch failed: %s", type(exc).__name__)
            return None
        finally:
            if owns_client:
                await client.aclose()


def parse_ical(raw: bytes) -> list[CalendarEvent]:
    """Parse an .ics payload into events.

    Kept module-level and pure so it can be tested against fixture bytes with no
    network. DTSTART is either a date (all-day) or a datetime (timed); the two are
    distinguished here rather than being coerced, because "all day" is information the
    caller wants.
    """
    cal = Calendar.from_ical(raw)
    events: list[CalendarEvent] = []

    for component in cal.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        value = dtstart.dt

        if isinstance(value, datetime):
            starts_at, all_day = value.date(), False
        elif isinstance(value, date):
            starts_at, all_day = value, True
        else:
            continue

        summary = component.get("SUMMARY")
        events.append(
            CalendarEvent(
                title=str(summary) if summary else "(no title)",
                starts_at=starts_at,
                all_day=all_day,
            )
        )

    return events
