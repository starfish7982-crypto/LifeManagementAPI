"""Shared dependency providers.

The integration clients are singletons because CalendarClient holds an in-process
cache; constructing a new one per request would make the TTL meaningless.
"""

from functools import lru_cache

from app.config import get_settings
from app.services.calendar import CalendarClient
from app.services.telegram import TelegramClient


@lru_cache
def get_telegram_client() -> TelegramClient:
    return TelegramClient(get_settings())


@lru_cache
def get_calendar_client() -> CalendarClient:
    return CalendarClient(get_settings())
