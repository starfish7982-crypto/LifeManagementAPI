"""Shared fixtures.

Each test gets its own in-memory SQLite database. StaticPool is required: without it
every connection would open a *different* in-memory database and the schema created
during setup would be invisible to the request handlers.

Tokens are obtained by actually calling /auth/register and /auth/login rather than by
constructing a JWT in the fixture. Minting tokens directly would mean the tests never
exercise the login path, and a bug in password verification would pass every one of
them. The cost is a couple of Argon2 hashes per test, which is the point of Argon2 and
is why `settings` lowers its cost parameters below.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app

TEST_JWT_SECRET = "test-secret-not-used-anywhere-real"
PRIMARY_USER = {"username": "sally@example.com", "password": "correct-horse-battery"}
OTHER_USER = {"username": "mallory@example.com", "password": "another-password-42"}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        jwt_secret=TEST_JWT_SECRET,
        telegram_bot_token="",
        telegram_chat_id="",
        google_calendar_ical_url="",
    )


@pytest.fixture
def unauthenticated_client(settings):
    """A client with no Authorization header, for testing the auth boundary itself."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def register_and_login(client: TestClient, credentials: dict) -> str:
    """Create an account and return its bearer token."""
    r = client.post(
        "/auth/register",
        json={"email": credentials["username"], "password": credentials["password"]},
    )
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data=credentials)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def client(unauthenticated_client):
    """The default client: signed in as the primary user."""
    token = register_and_login(unauthenticated_client, PRIMARY_USER)
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    return unauthenticated_client


@pytest.fixture
def other_client(client):
    """A second signed-in account sharing the same database as `client`.

    Used to prove isolation: anything this client can see, it must own. The shared
    database is the whole point — two users in two databases would pass every isolation
    test ever written, including a completely unscoped one. `app.dependency_overrides`
    is set by the `client` fixture and is global to the app, so a fresh TestClient over
    the same app reaches the same in-memory database.
    """
    second = TestClient(app)
    token = register_and_login(second, OTHER_USER)
    second.headers.update({"Authorization": f"Bearer {token}"})
    return second


@pytest.fixture
def snapshot_payload():
    return {
        "month": "2026-03-01",
        "note": "March",
        "items": [
            {"name": "Checking", "category": "cash", "amount": "4200.00"},
            {"name": "Brokerage", "category": "investments", "amount": "18500.50"},
            {"name": "Emergency fund", "category": "cash", "amount": "10000.00"},
        ],
    }
