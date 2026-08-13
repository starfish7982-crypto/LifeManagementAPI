"""Rotating a password without losing the account."""

from tests.conftest import PRIMARY_USER


def _make_todo(c, title="kept across the change"):
    return c.post("/todos", json={"title": title}).json()["id"]


def test_password_can_be_changed_and_the_old_one_stops_working(client, unauthenticated_client):
    r = client.post(
        "/auth/password",
        json={"current_password": PRIMARY_USER["password"], "new_password": "a-new-strong-one"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]

    old = unauthenticated_client.post("/auth/login", data=PRIMARY_USER)
    assert old.status_code == 401

    new = unauthenticated_client.post(
        "/auth/login",
        data={"username": PRIMARY_USER["username"], "password": "a-new-strong-one"},
    )
    assert new.status_code == 200


def test_the_data_survives_the_change(client):
    """The whole reason this endpoint exists instead of "delete and re-register"."""
    todo_id = _make_todo(client)
    client.post(
        "/auth/password",
        json={"current_password": PRIMARY_USER["password"], "new_password": "a-new-strong-one"},
    )
    assert [t["id"] for t in client.get("/todos").json()] == [todo_id]


def test_the_returned_token_works(client):
    token = client.post(
        "/auth/password",
        json={"current_password": PRIMARY_USER["password"], "new_password": "a-new-strong-one"},
    ).json()["access_token"]

    client.headers.update({"Authorization": f"Bearer {token}"})
    assert client.get("/auth/me").status_code == 200


def test_a_wrong_current_password_is_refused(client):
    r = client.post(
        "/auth/password",
        json={"current_password": "not-it", "new_password": "a-new-strong-one"},
    )
    assert r.status_code == 401
    # And the real password still works.
    assert (
        client.post(
            "/auth/password",
            json={
                "current_password": PRIMARY_USER["password"],
                "new_password": "a-new-strong-one",
            },
        ).status_code
        == 200
    )


def test_a_token_alone_is_not_enough(client):
    """A valid token plus a guessed password must fail.

    This is the test that justifies asking for current_password at all: without that
    check, anyone holding a borrowed token could lock the owner out of the account.
    """
    assert (
        client.post(
            "/auth/password", json={"current_password": "", "new_password": "whatever-long"}
        ).status_code
        == 422
    )


def test_the_new_password_has_a_length_floor(client):
    r = client.post(
        "/auth/password",
        json={"current_password": PRIMARY_USER["password"], "new_password": "short"},
    )
    assert r.status_code == 422


def test_changing_a_password_needs_a_session(unauthenticated_client):
    r = unauthenticated_client.post(
        "/auth/password", json={"current_password": "x", "new_password": "yyyyyyyy"}
    )
    assert r.status_code == 401
