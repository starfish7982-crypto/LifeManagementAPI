"""Application settings, loaded from environment variables (or a .env file).

Design note: settings are read once at import time and injected via `get_settings()`.
Tests override them with FastAPI's dependency_overrides rather than by mutating globals,
which keeps test runs independent of each other.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app/ -> the project root, the same walk main.py does to find web/dist.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # env_file is anchored for the same reason database_url below is: a relative path
    # here means .env is only found when the process happens to start in the root.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # Absolute, not `sqlite:///./life.db`.
    #
    # A relative path means "wherever this process was started from", so running
    # `uvicorn app.main:app` after a `cd web` silently opened a *different* database:
    # empty, schema created on the spot by the create_all in main.py, no accounts. The
    # app started fine and the only symptom was that the password no longer worked —
    # which reads as lost data rather than as a second file. The real one was untouched
    # a directory up. Anchoring it means there is one local database, wherever you
    # happen to be standing when you start the server.
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'life.db'}"

    # Signs access tokens. Anyone holding this value can mint a token for any account,
    # so it must be a real random secret in any deployment. The insecure default exists
    # so `uvicorn app.main:app` works on a fresh clone with no .env; `main.py` refuses
    # to start with it once DATABASE_URL points somewhere other than local SQLite.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 12 hours. There is no refresh token: a second token type roughly doubles the auth
    # surface, and for a single-user tool the cost of logging in again each day is lower
    # than the cost of getting refresh-token rotation subtly wrong.
    access_token_ttl_minutes: int = 720

    # Whether `POST /auth/register` will create an account.
    #
    # Defaults to closed, and the default is the whole point: this is a personal
    # deployment on a public URL, so an open endpoint means any stranger who finds it
    # can take a share of a free-tier instance and of a 0.5 GB database. Defaulting to
    # open and relying on the deployment to close it gets that backwards — the failure
    # mode of a forgotten setting should be "nobody can sign up", not "anybody can".
    #
    # Existing accounts are unaffected; this gates account creation only. Flip it to
    # true (an environment variable on the host, no code change) to let people in.
    allow_registration: bool = False

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    google_calendar_ical_url: str = ""
    calendar_cache_ttl_seconds: int = 900

    # Comma-separated so it can be set as a single environment variable on Render.
    # Empty by default: the UI ships from this same app, so nothing needs cross-origin
    # access until some other client does, and an origin list nobody uses is just an
    # opening left ajar.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_local_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.google_calendar_ical_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
