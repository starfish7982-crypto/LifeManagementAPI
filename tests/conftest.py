"""Shared fixtures.

Each test gets its own in-memory SQLite database. StaticPool is required: without it
every connection would open a *different* in-memory database and the schema created
during setup would be invisible to the request handlers.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app

TEST_API_KEY = "test-key"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key=TEST_API_KEY,
        database_url="sqlite://",
        telegram_bot_token="",
        telegram_chat_id="",
        google_calendar_ical_url="",
    )


@pytest.fixture
def client(settings):
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
        c.headers.update({"X-API-Key": TEST_API_KEY})
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


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
