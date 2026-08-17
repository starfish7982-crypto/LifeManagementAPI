"""Google Calendar integration over the secret iCal (.ics) URL.

Why iCal rather than the Google Calendar API: the API needs an OAuth consent screen,
a refresh-token store, and a Google Cloud project. The secret .ics URL is a single
read-only string, which is the right amount of machinery for reading one personal
calendar. The trade-off is stated so the choice is visibly deliberate, not lazy.

The feed is cached in memory until the user explicitly refreshes it. Google rate-limits
these URLs, and a dashboard that refreshes on every page load would otherwise hit them
constantly — while a calendar is personal enough that silently replacing what the user
just reviewed is usually surprising.
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
    """Reads one calendar feed.

    Takes the URL rather than the application Settings: the feed is now a per-user
    value stored in the database, and a client that reaches into global configuration
    could only ever serve one calendar for the whole service. That was the bug — every
    account saw the same events, because there was only one URL.
    """

    def __init__(
        self,
        ical_url: str,
        cache_ttl_seconds: int = 900,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._ical_url = ical_url
        # Kept in the constructor for backwards-compatible dependency wiring. The
        # cache is intentionally not time-expiring; only force_refresh invalidates it.
        self._ttl = cache_ttl_seconds
        self._client = client
        self._cache: _CacheEntry | None = None

    @classmethod
    def from_settings(cls, settings: Settings, client: httpx.AsyncClient | None = None):
        """Build from the environment. Used as a fallback when a user has set nothing."""
        return cls(
            settings.google_calendar_ical_url,
            settings.calendar_cache_ttl_seconds,
            client=client,
        )

    @property
    def enabled(self) -> bool:
        return bool(self._ical_url)

    def _cache_is_fresh(self) -> bool:
        return self._cache is not None

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

    async def events_between(
        self, start: date, end: date, *, force_refresh: bool = False
    ) -> list[CalendarEvent]:
        """Return the cached feed's events from start through end, in calendar order."""
        if end < start:
            return []

        # Loading via events_on keeps all cache-refresh and failure behavior in one
        # place.  Its one-day return value is deliberately ignored here.
        await self.events_on(start, force_refresh=force_refresh)
        if self._cache is None:
            return []
        return sorted(
            (e for e in self._cache.events if start <= e.starts_at <= end),
            key=lambda e: (e.starts_at, e.title.casefold()),
        )

    async def events_starting_between(self, start: date, end: date) -> list[CalendarEvent]:
        """Calendar events whose check-in/start date is inside a lodging range."""
        return await self.events_between(start, end)

    async def _fetch(self) -> list[CalendarEvent] | None:
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        owns_client = self._client is None
        try:
            resp = await client.get(self._ical_url)
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
            starts_time = value.timetz().replace(tzinfo=None)
        elif isinstance(value, date):
            starts_at, all_day = value, True
            starts_time = None
        else:
            continue

        dtend = component.get("DTEND")
        end_value = dtend.dt if dtend is not None else None
        if isinstance(end_value, datetime):
            ends_at = end_value.date()
        elif isinstance(end_value, date):
            ends_at = end_value
        else:
            ends_at = None

        summary = component.get("SUMMARY")
        uid = component.get("UID")
        recurrence_id = component.get("RECURRENCE-ID")
        description = component.get("DESCRIPTION")
        location = component.get("LOCATION")
        events.append(
            CalendarEvent(
                uid=(
                    f"{uid}|{recurrence_id}"
                    if uid and recurrence_id
                    else str(uid)
                    if uid
                    else None
                ),
                title=str(summary) if summary else "(no title)",
                starts_at=starts_at,
                starts_time=starts_time,
                ends_at=ends_at,
                all_day=all_day,
                description=str(description) if description else None,
                location=str(location) if location else None,
            )
        )

    return events
