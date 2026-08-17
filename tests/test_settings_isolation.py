"""Integration settings, and the leak that moving them into the database closed.

Before accounts existed, the calendar feed and the Telegram credentials were
environment variables — one set for the whole service. Adding accounts did not change
that, so every signed-in user's /today was built from whichever calendar the operator
had configured. These tests are the reason to believe that is fixed.
"""

import httpx
import pytest
import respx

from tests.conftest import OTHER_USER, PRIMARY_USER

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Sally's dentist
DTSTART;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""

OTHER_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Mallory's meeting
DTSTART;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""


def test_settings_start_empty(client):
    body = client.get("/settings").json()
    assert body == {
        "telegram_configured": False,
        "telegram_chat_id": None,
        "google_calendar_ical_url": None,
        "updated_at": None,
    }


def test_the_bot_token_is_never_returned(client):
    """Write-only by design: the screen needs "configured", not the secret."""
    client.patch(
        "/settings",
        json={"telegram_bot_token": "123:super-secret", "telegram_chat_id": "42"},
    )
    body = client.get("/settings")
    assert "super-secret" not in body.text
    assert body.json()["telegram_configured"] is True
    assert body.json()["telegram_chat_id"] == "42"


def test_patch_leaves_unmentioned_fields_alone(client):
    """The regression this guards: saving the calendar URL wiping the bot token,
    because the form never had a field to send it back in."""
    client.patch("/settings", json={"telegram_bot_token": "123:abc", "telegram_chat_id": "42"})
    client.patch("/settings", json={"google_calendar_ical_url": "https://example.test/c.ics"})

    body = client.get("/settings").json()
    assert body["telegram_configured"] is True
    assert body["google_calendar_ical_url"] == "https://example.test/c.ics"


def test_an_explicit_empty_string_clears_a_field(client):
    client.patch("/settings", json={"google_calendar_ical_url": "https://example.test/c.ics"})
    client.patch("/settings", json={"google_calendar_ical_url": ""})
    assert client.get("/settings").json()["google_calendar_ical_url"] is None


def test_disconnecting_telegram_clears_both_halves(client):
    client.patch("/settings", json={"telegram_bot_token": "123:abc", "telegram_chat_id": "42"})
    assert client.delete("/settings/telegram").status_code == 204

    body = client.get("/settings").json()
    assert body["telegram_configured"] is False
    assert body["telegram_chat_id"] is None


@pytest.mark.parametrize("bad", ["file:///etc/passwd", "javascript:alert(1)", "ftp://x/y.ics"])
def test_the_calendar_url_must_be_http(client, bad):
    """The server fetches this URL. Without a scheme check, `file:///etc/passwd` is a
    request to read the container's filesystem through the API."""
    assert client.patch("/settings", json={"google_calendar_ical_url": bad}).status_code == 422


def test_settings_do_not_leak_between_accounts(client, other_client):
    client.patch(
        "/settings",
        json={
            "telegram_bot_token": "123:sallys",
            "telegram_chat_id": "111",
            "google_calendar_ical_url": "https://example.test/sally.ics",
        },
    )

    theirs = other_client.get("/settings").json()
    assert theirs["telegram_configured"] is False
    assert theirs["telegram_chat_id"] is None
    assert theirs["google_calendar_ical_url"] is None


@pytest.mark.asyncio
@respx.mock
async def test_today_uses_the_callers_own_calendar(client, other_client):
    """The leak, stated as a test.

    Two accounts, two calendars, one request each. Before the settings moved into the
    database there was only one URL in the whole process, so both of these returned the
    same events — and the second user had never configured anything at all.
    """
    respx.get("https://example.test/sally.ics").mock(
        return_value=httpx.Response(200, content=ICS)
    )
    respx.get("https://example.test/mallory.ics").mock(
        return_value=httpx.Response(200, content=OTHER_ICS)
    )

    client.patch("/settings", json={"google_calendar_ical_url": "https://example.test/sally.ics"})
    other_client.patch(
        "/settings", json={"google_calendar_ical_url": "https://example.test/mallory.ics"}
    )

    mine = client.get("/today?day=2026-03-02").json()["calendar_events"]
    theirs = other_client.get("/today?day=2026-03-02").json()["calendar_events"]

    assert [e["title"] for e in mine] == ["Sally's dentist"]
    assert [e["title"] for e in theirs] == ["Mallory's meeting"]


@pytest.mark.asyncio
async def test_a_user_with_no_calendar_sees_no_events(client, other_client):
    """The other half of the leak: an account that configured nothing should get an
    empty list, not somebody else's calendar."""
    client.patch("/settings", json={"google_calendar_ical_url": "https://example.test/s.ics"})
    assert other_client.get("/today").json()["calendar_events"] == []


def test_the_test_endpoint_reports_an_unconfigured_integration(client):
    assert client.post("/settings/telegram/test").json()["detail"] == "Telegram is not configured"


def test_settings_need_a_session(unauthenticated_client):
    assert unauthenticated_client.get("/settings").status_code == 401
    assert unauthenticated_client.patch("/settings", json={}).status_code == 401


def test_two_accounts_really_are_distinct(client, other_client):
    assert client.get("/auth/me").json()["username"] == PRIMARY_USER["username"]
    assert other_client.get("/auth/me").json()["username"] == OTHER_USER["username"]
