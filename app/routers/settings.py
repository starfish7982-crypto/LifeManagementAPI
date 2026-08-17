"""Per-user integration settings.

The Telegram bot token is write-only: it can be set and cleared, never read back. A
screen needs to know whether one is configured, not what it is, and a value that comes
back in a response has been through the browser's memory, any intermediate cache, and
any log that records bodies. `UserSettingsOut` reports `telegram_configured` instead.

Sending an explicit empty string clears a field; omitting it leaves it alone. That
distinction is why the update is a PATCH over `exclude_unset` rather than a PUT — a PUT
would make "I only wanted to change my chat id" silently erase the token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_telegram_client, settings_for
from app.models import User, UserSettings
from app.schemas import Message, UserSettingsIn, UserSettingsOut
from app.security import current_user
from app.services.telegram import TelegramClient

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(row: UserSettings | None) -> UserSettingsOut:
    if row is None:
        return UserSettingsOut(
            telegram_configured=False,
            telegram_chat_id=None,
            google_calendar_ical_url=None,
            updated_at=None,
        )
    return UserSettingsOut(
        telegram_configured=bool(row.telegram_bot_token),
        telegram_chat_id=row.telegram_chat_id,
        google_calendar_ical_url=row.google_calendar_ical_url,
        updated_at=row.updated_at,
    )


@router.get("", response_model=UserSettingsOut)
def get_settings_for_user(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UserSettingsOut:
    return _to_out(settings_for(db, user))


@router.patch("", response_model=UserSettingsOut)
def update_settings(
    payload: UserSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UserSettingsOut:
    row = settings_for(db, user)
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)

    # exclude_unset distinguishes "not mentioned" from "set to empty". Without it,
    # saving the calendar URL would wipe the Telegram token the form never showed.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value or None)

    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/telegram/test", response_model=Message)
async def send_test_message(
    telegram: TelegramClient = Depends(get_telegram_client),
) -> Message:
    """Prove the credentials work, from the server, where the token lives.

    Worth its own endpoint: a bot token and a chat id are two opaque strings that fail
    silently when wrong, and "did it work?" is otherwise only answerable by waiting for
    tomorrow's digest not to arrive.
    """
    if not telegram.enabled:
        return Message(detail="Telegram is not configured")
    delivered = await telegram.send_message("✅ LifeManagement test message")
    if delivered:
        return Message(detail="Test message sent")
    return Message(detail="Could not deliver — check the bot token and chat id")


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
def clear_telegram(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Explicit disconnect. Clearing a credential should not require guessing that an
    empty string in a text field is how you do it."""
    row = settings_for(db, user)
    if row is not None:
        row.telegram_bot_token = None
        row.telegram_chat_id = None
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
