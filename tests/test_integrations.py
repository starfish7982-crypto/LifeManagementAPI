"""Integration-layer tests.

No network is touched. respx intercepts httpx at the transport layer, which lets the
real client code run (retry loop, status handling, escaping) against scripted responses.
Mocking our own client instead would test nothing.
"""

from datetime import date, time

import httpx
import pytest
import respx

from app.services.calendar import CalendarClient, parse_ical
from app.services.telegram import TelegramClient

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Dentist
DTSTART:20260302T140000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Public holiday
DTSTART;VALUE=DATE:20260303
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260304
END:VEVENT
END:VCALENDAR
"""

HOTEL_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Reservation at Residence Inn Toronto
DTSTART;VALUE=DATE:20260820
DTEND;VALUE=DATE:20260822
LOCATION:255 Wellington St W, Toronto
DESCRIPTION:Confirmation number: ABCD-1234\\nPhone: +1 416 555 0100
END:VEVENT
END:VCALENDAR
"""


# ------------------------------------------------------------------ iCal parsing


def test_parse_ical_distinguishes_timed_and_all_day():
    events = parse_ical(ICS)
    by_title = {e.title: e for e in events}

    assert by_title["Dentist"].starts_at == date(2026, 3, 2)
    assert by_title["Dentist"].starts_time == time(14, 0)
    assert by_title["Dentist"].all_day is False
    assert by_title["Public holiday"].all_day is True


def test_parse_ical_handles_missing_summary():
    events = parse_ical(ICS)
    assert any(e.title == "(no title)" for e in events)


def test_parse_ical_keeps_hotel_details_for_the_lodging_import():
    event = parse_ical(HOTEL_ICS)[0]
    assert event.ends_at == date(2026, 8, 22)
    assert event.location == "255 Wellington St W, Toronto"
    assert "ABCD-1234" in (event.description or "")


# ---------------------------------------------------------------- calendar client


@pytest.mark.asyncio
@respx.mock
async def test_calendar_caches_between_calls():
    route = respx.get("https://example.test/cal.ics").mock(
        return_value=httpx.Response(200, content=ICS)
    )
    async with httpx.AsyncClient() as http:
        client = CalendarClient("https://example.test/cal.ics", client=http)
        assert len(await client.events_on(date(2026, 3, 2))) == 1
        await client.events_on(date(2026, 3, 3))

    assert route.call_count == 1, "second lookup should be served from cache"


@pytest.mark.asyncio
@respx.mock
async def test_calendar_serves_stale_cache_when_upstream_fails():
    respx.get("https://example.test/cal.ics").mock(return_value=httpx.Response(200, content=ICS))

    async with httpx.AsyncClient() as http:
        client = CalendarClient("https://example.test/cal.ics", client=http)
        assert len(await client.events_on(date(2026, 3, 2))) == 1

        respx.get("https://example.test/cal.ics").mock(side_effect=httpx.ConnectError("down"))
        # An explicit refresh degrades to stale data rather than returning nothing.
        assert len(await client.events_on(date(2026, 3, 2), force_refresh=True)) == 1


@pytest.mark.asyncio
@respx.mock
async def test_calendar_only_fetches_again_when_explicitly_refreshed():
    route = respx.get("https://example.test/cal.ics").mock(
        return_value=httpx.Response(200, content=ICS)
    )
    async with httpx.AsyncClient() as http:
        # The old TTL setting cannot cause a background re-fetch any more.
        client = CalendarClient("https://example.test/cal.ics", cache_ttl_seconds=0, client=http)
        await client.events_on(date(2026, 3, 2))
        await client.events_on(date(2026, 3, 3))
        assert route.call_count == 1
        await client.events_on(date(2026, 3, 2), force_refresh=True)

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_calendar_disabled_returns_empty():
    client = CalendarClient("")
    assert await client.events_on(date(2026, 3, 2)) == []


# ---------------------------------------------------------------- telegram client


def _telegram() -> tuple[str, str]:
    return ("123:abc", "42")


@pytest.mark.asyncio
@respx.mock
async def test_telegram_sends_successfully():
    route = respx.post("https://api.telegram.org/bot123:abc/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    async with httpx.AsyncClient() as http:
        assert await TelegramClient(*_telegram(), client=http).send_message("hi") is True
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_telegram_does_not_retry_client_errors():
    route = respx.post("https://api.telegram.org/bot123:abc/sendMessage").mock(
        return_value=httpx.Response(400, json={"ok": False, "description": "chat not found"})
    )
    async with httpx.AsyncClient() as http:
        assert await TelegramClient(*_telegram(), client=http).send_message("hi") is False
    assert route.call_count == 1, "a 400 is not worth retrying"


@pytest.mark.asyncio
@respx.mock
async def test_telegram_retries_server_errors_then_gives_up(monkeypatch):
    monkeypatch.setattr("app.services.telegram.asyncio.sleep", _no_sleep)
    route = respx.post("https://api.telegram.org/bot123:abc/sendMessage").mock(
        return_value=httpx.Response(503)
    )
    async with httpx.AsyncClient() as http:
        assert await TelegramClient(*_telegram(), client=http).send_message("hi") is False
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_telegram_recovers_on_a_later_attempt(monkeypatch):
    monkeypatch.setattr("app.services.telegram.asyncio.sleep", _no_sleep)
    respx.post("https://api.telegram.org/bot123:abc/sendMessage").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
    )
    async with httpx.AsyncClient() as http:
        assert await TelegramClient(*_telegram(), client=http).send_message("hi") is True


@pytest.mark.asyncio
async def test_telegram_disabled_is_a_no_op():
    assert await TelegramClient("", "").send_message("hi") is False


async def _no_sleep(_seconds: float) -> None:
    return None
