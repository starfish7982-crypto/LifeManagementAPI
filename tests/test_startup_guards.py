"""The boot-time refusal to run with a development signing secret.

Worth a test because it is a guard that only fires in an environment the test suite
never runs in — exactly the kind of code that rots unnoticed. If it stops working, the
symptom in production is silent: tokens signed with a publicly known secret.
"""

import pytest

from app.config import Settings
from app.main import DEV_JWT_SECRET


def _would_refuse(settings: Settings) -> bool:
    """Mirror of the condition in `main.lifespan`."""
    return not settings.is_local_sqlite and settings.jwt_secret == DEV_JWT_SECRET


def test_dev_secret_against_postgres_is_refused():
    assert _would_refuse(
        Settings(database_url="postgresql://u:p@host/db", jwt_secret=DEV_JWT_SECRET)
    )


def test_dev_secret_against_local_sqlite_is_allowed():
    """A fresh clone must run with no .env, or the quickstart in the README is a lie."""
    assert not _would_refuse(
        Settings(database_url="sqlite:///./life.db", jwt_secret=DEV_JWT_SECRET)
    )


def test_real_secret_against_postgres_is_allowed():
    assert not _would_refuse(
        Settings(database_url="postgresql://u:p@host/db", jwt_secret="a-real-random-secret")
    )


@pytest.mark.asyncio
async def test_lifespan_raises_rather_than_starting(monkeypatch):
    """The guard is exercised through the real startup path, not just its condition."""
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
    monkeypatch.setenv("JWT_SECRET", DEV_JWT_SECRET)

    with pytest.raises(RuntimeError, match="JWT_SECRET is still the development default"):
        async with main.lifespan(main.app):
            pass

    get_settings.cache_clear()
