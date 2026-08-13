"""Cross-account isolation.

These are the tests that justify the `user_id` column existing. Every one of them
passes trivially if the two clients use separate databases, so `other_client` shares
one with `client` on purpose — see the fixture.

The shape of each test is the same: user A creates something, then user B tries to see
or touch it and must fail as though it were never there.
"""

import pytest


def _make_todo(c, title="A's private todo"):
    r = c.post("/todos", json={"title": title})
    assert r.status_code == 201
    return r.json()["id"]


def _make_reminder(c, title="A's private reminder"):
    r = c.post("/reminders", json={"title": title, "frequency": "monthly", "day_of_month": 1})
    assert r.status_code == 201
    return r.json()["id"]


def _make_snapshot(c, payload):
    r = c.post("/assets/snapshots", json=payload)
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------- todos


def test_listing_todos_shows_only_your_own(client, other_client):
    _make_todo(client, "belongs to sally")
    _make_todo(other_client, "belongs to mallory")

    mine = client.get("/todos").json()
    theirs = other_client.get("/todos").json()

    assert [t["title"] for t in mine] == ["belongs to sally"]
    assert [t["title"] for t in theirs] == ["belongs to mallory"]


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("patch", {"json": {"done": True}}),
        ("delete", {}),
    ],
)
def test_another_users_todo_cannot_be_written(client, other_client, method, kwargs):
    todo_id = _make_todo(client)
    resp = getattr(other_client, method)(f"/todos/{todo_id}", **kwargs)
    # 404, not 403: 403 would confirm the row exists.
    assert resp.status_code == 404
    # And the original is untouched.
    assert client.get("/todos").json()[0]["done"] is False


# ------------------------------------------------------------------------ reminders


def test_listing_reminders_shows_only_your_own(client, other_client):
    _make_reminder(client, "sally's reminder")
    _make_reminder(other_client, "mallory's reminder")

    assert [r["title"] for r in client.get("/reminders").json()] == ["sally's reminder"]
    assert [r["title"] for r in other_client.get("/reminders").json()] == [
        "mallory's reminder"
    ]


def test_another_users_reminder_is_not_readable(client, other_client):
    reminder_id = _make_reminder(client)
    assert other_client.get(f"/reminders/{reminder_id}").status_code == 404
    assert other_client.delete(f"/reminders/{reminder_id}").status_code == 404


# --------------------------------------------------------------------------- assets


def test_another_users_snapshot_is_not_readable(client, other_client, snapshot_payload):
    snapshot_id = _make_snapshot(client, snapshot_payload)

    assert other_client.get(f"/assets/snapshots/{snapshot_id}").status_code == 404
    assert other_client.get(f"/assets/snapshots/{snapshot_id}/categories").status_code == 404
    assert other_client.delete(f"/assets/snapshots/{snapshot_id}").status_code == 404
    assert (
        other_client.put(f"/assets/snapshots/{snapshot_id}", json=snapshot_payload).status_code
        == 404
    )


def test_the_same_month_is_available_to_every_user(client, other_client, snapshot_payload):
    """The uniqueness constraint is per user.

    When it was UNIQUE(month) alone, the second account on the system could not record
    March because the first one already had — one user's data silently constrained
    another's. This is the regression test for that.
    """
    assert client.post("/assets/snapshots", json=snapshot_payload).status_code == 201
    assert other_client.post("/assets/snapshots", json=snapshot_payload).status_code == 201

    # Still a conflict within a single account.
    assert client.post("/assets/snapshots", json=snapshot_payload).status_code == 409


def test_snapshot_totals_do_not_mix_accounts(client, other_client, snapshot_payload):
    _make_snapshot(client, snapshot_payload)
    other_id = _make_snapshot(other_client, {**snapshot_payload, "items": []})

    assert other_client.get(f"/assets/snapshots/{other_id}/categories").json() == []


# ---------------------------------------------------------------------------- today


def test_today_aggregates_only_your_own_rows(client, other_client):
    _make_todo(client, "sally's task")
    _make_todo(other_client, "mallory's task")

    mine = client.get("/today").json()
    assert [t["title"] for t in mine["todos"]] == ["sally's task"]
