"""Application settings, loaded from environment variables (or a .env file).

Design note: settings are read once at import time and injected via `get_settings()`.
Tests override them with FastAPI's dependency_overrides rather than by mutating globals,
which keeps test runs independent of each other.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = "dev-key-change-me"
    database_url: str = "sqlite:///./life.db"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    google_calendar_ical_url: str = ""
    calendar_cache_ttl_seconds: int = 900

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.google_calendar_ical_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
