"""The authentication boundary: who gets in, who does not, and what leaks."""

from datetime import datetime, timedelta, timezone

import jwt

from tests.conftest import OTHER_USER, PRIMARY_USER, TEST_JWT_SECRET


def test_health_needs_no_token(unauthenticated_client):
    resp = unauthenticated_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_schema_is_served(unauthenticated_client):
    resp = unauthenticated_client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/assets/snapshots" in resp.json()["paths"]


def test_protected_route_rejects_missing_token(unauthenticated_client):
    assert unauthenticated_client.get("/todos").status_code == 401


def test_protected_route_rejects_garbage_token(unauthenticated_client):
    unauthenticated_client.headers.update({"Authorization": "Bearer not-a-jwt"})
    assert unauthenticated_client.get("/todos").status_code == 401


def test_register_then_login_returns_usable_token(unauthenticated_client):
    r = unauthenticated_client.post(
        "/auth/register",
        json={"username": PRIMARY_USER["username"], "password": PRIMARY_USER["password"]},
    )
    assert r.status_code == 201
    assert "password" not in r.text and "hash" not in r.text

    r = unauthenticated_client.post("/auth/login", data=PRIMARY_USER)
    assert r.status_code == 200
    token = r.json()["access_token"]

    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    assert unauthenticated_client.get("/todos").status_code == 200


def test_duplicate_registration_is_409(unauthenticated_client):
    body = {"username": PRIMARY_USER["username"], "password": PRIMARY_USER["password"]}
    assert unauthenticated_client.post("/auth/register", json=body).status_code == 201
    assert unauthenticated_client.post("/auth/register", json=body).status_code == 409


def test_username_is_normalised_so_case_cannot_fork_an_account(unauthenticated_client):
    unauthenticated_client.post(
        "/auth/register",
        json={"username": "Sally", "password": PRIMARY_USER["password"]},
    )
    # Same account, entered differently.
    r = unauthenticated_client.post(
        "/auth/login",
        data={"username": "sally", "password": PRIMARY_USER["password"]},
    )
    assert r.status_code == 200


def test_wrong_password_is_rejected(unauthenticated_client):
    unauthenticated_client.post(
        "/auth/register",
        json={"username": PRIMARY_USER["username"], "password": PRIMARY_USER["password"]},
    )
    r = unauthenticated_client.post(
        "/auth/login",
        data={"username": PRIMARY_USER["username"], "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_does_not_reveal_whether_the_account_exists(unauthenticated_client):
    """A wrong password and an unknown username must be indistinguishable to the caller."""
    unauthenticated_client.post(
        "/auth/register",
        json={"username": PRIMARY_USER["username"], "password": PRIMARY_USER["password"]},
    )
    known = unauthenticated_client.post(
        "/auth/login", data={"username": PRIMARY_USER["username"], "password": "wrong"}
    )
    unknown = unauthenticated_client.post(
        "/auth/login", data={"username": "nobody", "password": "wrong"}
    )
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_short_password_is_rejected(unauthenticated_client):
    r = unauthenticated_client.post(
        "/auth/register", json={"username": "valid-user", "password": "short"}
    )
    assert r.status_code == 422


def test_expired_token_is_rejected(unauthenticated_client):
    """Signed correctly, but past its exp. Signature validity is not enough."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "1", "iat": past - timedelta(hours=1), "exp": past},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    assert unauthenticated_client.get("/todos").status_code == 401


def test_token_signed_with_another_secret_is_rejected(unauthenticated_client):
    token = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "an-attackers-own-secret",
        algorithm="HS256",
    )
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    assert unauthenticated_client.get("/todos").status_code == 401


def test_alg_none_token_is_rejected(unauthenticated_client):
    """The classic JWT attack: drop the signature and declare the algorithm 'none'.

    Rejected because `jwt.decode` is called with an explicit `algorithms` whitelist
    rather than trusting the token's own header.
    """
    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        key="",
        algorithm="none",
    )
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    assert unauthenticated_client.get("/todos").status_code == 401


def test_token_for_a_deleted_user_is_rejected(unauthenticated_client):
    """A token stays syntactically valid until it expires, so `current_user` re-reads
    the row. Without that lookup a closed account would keep working for 12 hours."""
    token = jwt.encode(
        {
            "sub": "99999",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    assert unauthenticated_client.get("/todos").status_code == 401


def test_me_returns_the_signed_in_account(client):
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == PRIMARY_USER["username"]
    assert "password_hash" not in r.json()


def test_two_accounts_get_different_identities(client, other_client):
    assert client.get("/auth/me").json()["username"] == PRIMARY_USER["username"]
    assert other_client.get("/auth/me").json()["username"] == OTHER_USER["username"]
