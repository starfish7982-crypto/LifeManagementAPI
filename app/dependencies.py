"""Per-user integration clients.

These used to be `@lru_cache` singletons built from the application Settings, which
meant one calendar feed and one Telegram chat for the whole service. Once accounts
existed that stopped being a simplification and became a leak: any signed-in user
calling /today saw the events from whichever calendar the operator had configured.

Calendar data now comes only from the caller's own `user_settings` row.  A server-wide
fallback is surprising in a personal app: it can make a newly created account appear to
have somebody else's test calendar before the owner connects their own.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User, UserSettings
from app.security import current_user
from app.services.calendar import CalendarClient
from app.services.telegram import TelegramClient


def settings_for(db: Session, user: User) -> UserSettings | None:
    return db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))


@lru_cache(maxsize=64)
def _calendar_for(ical_url: str, ttl_seconds: int) -> CalendarClient:
    """One client per feed URL, kept so its TTL cache survives between requests.

    Keyed on the URL rather than on the user: the cache holds the parsed contents of
    that feed, which are the same whoever asked for them. Two accounts pointing at a
    shared family calendar get one set of fetches rather than two.

    The bound matters. An unbounded cache keyed by a user-supplied string is a slow
    memory leak that any account could drive by editing its settings repeatedly.
    """
    return CalendarClient(ical_url, ttl_seconds)


def get_calendar_client(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> CalendarClient:
    row = settings_for(db, user)
    url = row.google_calendar_ical_url if row else None
    if not url:
        # A disabled client rather than None: `/today` should return an empty event
        # list, not branch on whether the integration exists.
        return CalendarClient("")
    return _calendar_for(url, settings.calendar_cache_ttl_seconds)


def get_telegram_client(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> TelegramClient:
    row = settings_for(db, user)
    token = (row.telegram_bot_token if row else None) or settings.telegram_bot_token
    chat = (row.telegram_chat_id if row else None) or settings.telegram_chat_id
    # Not cached: it holds no state worth keeping, and caching a bot token by value
    # would keep a credential alive in memory after the user had removed it.
    return TelegramClient(token, chat)
