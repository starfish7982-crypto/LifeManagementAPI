"""Application settings, loaded from environment variables (or a .env file).

Design note: settings are read once at import time and injected via `get_settings()`.
Tests override them with FastAPI's dependency_overrides rather than by mutating globals,
which keeps test runs independent of each other.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./life.db"

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
