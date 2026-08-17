"""Registration is closed unless the deployment opens it.

The rest of the suite runs with `allow_registration=True`, because almost every test
needs an account to get a token. That makes this file the only place the shipped
default is actually exercised, so it checks the default itself rather than trusting
the fixture — a regression that flipped `Settings.allow_registration` to True would
otherwise be invisible until strangers turned up on the deployed instance.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from tests.conftest import PRIMARY_USER, TEST_JWT_SECRET

NEWCOMER = {"username": "stranger", "password": "a-perfectly-fine-password"}


@pytest.fixture
def closed_client():
    """A client against an instance that has NOT opened registration."""
    settings = Settings(
        database_url="sqlite://",
        jwt_secret=TEST_JWT_SECRET,
        allow_registration=False,
        telegram_bot_token="",
        telegram_chat_id="",
        google_calendar_ical_url="",
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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


def test_the_shipped_default_is_closed():
    """The default carries the security property, so it is asserted directly."""
    assert Settings(database_url="sqlite://").allow_registration is False


def test_registration_is_refused_when_closed(closed_client):
    r = closed_client.post("/auth/register", json=NEWCOMER)
    assert r.status_code == 403
    assert "closed" in r.json()["detail"].lower()


def test_nothing_is_created_when_registration_is_refused(closed_client):
    closed_client.post("/auth/register", json=NEWCOMER)
    # The account must not exist afterwards, which logging in is the honest way to
    # check: a 201 that quietly rolled back would still fail here.
    r = closed_client.post("/auth/login", data=NEWCOMER)
    assert r.status_code == 401


def test_a_closed_instance_does_not_reveal_which_names_are_taken(closed_client):
    """403 comes before the lookup, so taken and free names are indistinguishable.

    Returning 409 for an existing account and 403 for a new one would turn a closed
    endpoint into a working account-name oracle.
    """
    closed = closed_client.post("/auth/register", json=NEWCOMER)

    # Create a real account through a separately opened instance sharing this database.
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, allow_registration=True
    )
    with TestClient(app) as opened:
        assert opened.post("/auth/register", json=PRIMARY_USER).status_code == 201

    # Close it again and ask about the name that now exists.
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, allow_registration=False
    )
    with TestClient(app) as reclosed:
        taken = reclosed.post("/auth/register", json=PRIMARY_USER)

    assert taken.status_code == closed.status_code == 403
    assert taken.json() == closed.json()


def test_existing_accounts_still_sign_in_when_registration_is_closed(closed_client):
    """The gate is on account creation only — it must not lock out the owner."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, allow_registration=True
    )
    with TestClient(app) as opened:
        assert opened.post("/auth/register", json=PRIMARY_USER).status_code == 201

    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, allow_registration=False
    )
    with TestClient(app) as reclosed:
        r = reclosed.post("/auth/login", data=PRIMARY_USER)
        assert r.status_code == 200
        assert r.json()["access_token"]


def test_config_endpoint_reports_closed(closed_client):
    r = closed_client.get("/auth/config")
    assert r.status_code == 200
    assert r.json() == {"registration_open": False}


def test_config_endpoint_reports_open(unauthenticated_client):
    """The `settings` fixture opens registration, so this is the other branch."""
    r = unauthenticated_client.get("/auth/config")
    assert r.status_code == 200
    assert r.json() == {"registration_open": True}


def test_config_endpoint_needs_no_token(closed_client):
    """The sign-in screen reads it before anyone has a token."""
    assert "Authorization" not in closed_client.headers
    assert closed_client.get("/auth/config").status_code == 200
