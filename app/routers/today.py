"""The aggregate endpoint: everything happening today, from three sources.

This is the piece that makes the project an *integration* service rather than three
independent CRUD tables. It joins local database state with a third-party calendar
feed, and can push the result to Telegram.
"""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_calendar_client, get_telegram_client
from app.models import Reminder, Todo, User
from app.routers.reminders import _to_out, is_within_lead_time
from app.schemas import Message, TodayOut, TodoOut
from app.security import current_user
from app.services.calendar import CalendarClient
from app.services.telegram import TelegramClient

router = APIRouter(prefix="/today", tags=["today"])


def _calendar_event_key(event) -> str:
    """A stable key for deduplicating calendar events that become app todos."""
    if event.uid:
        return f"calendar:{event.uid}:{event.starts_at.isoformat()}"[:255]
    # iCal UIDs are expected, but a handful of exported feeds omit them.  Hashing the
    # stable visible fields is preferable to creating duplicates every time that feed
    # is opened.
    raw = f"{event.title}\0{event.starts_at.isoformat()}\0{event.ends_at or ''}"
    return f"calendar:derived:{sha256(raw.encode()).hexdigest()}"


def _add_today_calendar_todos(db: Session, user: User, day: date, events) -> None:
    """Create one checkable app todo for each activity that starts today.

    This is deliberately append-only.  Checking the task marks it complete locally;
    it never changes the Google event, and revisiting the page finds its stored key
    rather than creating it again.
    """
    today_events = [event for event in events if event.starts_at == day]
    if not today_events:
        return
    keys = {_calendar_event_key(event) for event in today_events}
    existing = {
        todo.calendar_event_key: todo
        for todo in db.scalars(
            select(Todo).where(
                Todo.user_id == user.id, Todo.calendar_event_key.in_(keys)
            )
        )
    }
    highest = db.scalar(
        select(func.max(Todo.position)).where(Todo.user_id == user.id, Todo.bucket == "today")
    )
    position = 0 if highest is None else highest + 1
    for event in today_events:
        key = _calendar_event_key(event)
        if key in existing:
            existing[key].calendar_time = event.starts_time
            continue
        db.add(
            Todo(
                user_id=user.id,
                title=event.title[:200],
                due_date=day,
                bucket="today",
                position=position,
                source="calendar",
                calendar_event_key=key,
                calendar_time=event.starts_time,
            )
        )
        position += 1
    db.commit()


async def _build_today(
    db: Session,
    calendar: CalendarClient,
    day: date,
    user: User,
    refresh_calendar: bool = False,
) -> TodayOut:
    # One cached feed powers the entire week.  Today's activities are also captured as
    # checkable local todos before the todo query below, so the response is complete on
    # the same request that first sees the calendar event.
    events = await calendar.events_between(
        day, day + timedelta(days=7), force_refresh=refresh_calendar
    )
    _add_today_calendar_todos(db, user, day, events)

    todos = list(
        db.scalars(
            select(Todo)
            .where(Todo.user_id == user.id)
            .where(Todo.done.is_(False))
            .where(or_(Todo.due_date.is_(None), Todo.due_date <= day))
            .order_by(Todo.due_date.is_(None), Todo.due_date, Todo.id)
        )
    )

    # `is_within_lead_time` rather than `next_due == day`: a reminder with a lead time
    # is meant to appear during the run-up, not only on the deadline itself.
    reminders = [
        out
        for out in (
            _to_out(r, day)
            for r in db.scalars(
                select(Reminder).where(Reminder.user_id == user.id, Reminder.active)
            )
        )
        if is_within_lead_time(out)
    ]

    return TodayOut(
        date=day,
        todos=[TodoOut.model_validate(t) for t in todos],
        reminders_due=reminders,
        calendar_events=events,
    )


@router.get("", response_model=TodayOut)
async def get_today(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    calendar: CalendarClient = Depends(get_calendar_client),
    day: date | None = Query(None, description="Override the date; defaults to today"),
    refresh_calendar: bool = Query(False, description="Bypass the calendar cache"),
) -> TodayOut:
    return await _build_today(db, calendar, day or date.today(), user, refresh_calendar)


@router.post("/notify", response_model=Message)
async def notify_today(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    calendar: CalendarClient = Depends(get_calendar_client),
    telegram: TelegramClient = Depends(get_telegram_client),
    day: date | None = Query(None),
) -> Message:
    """Push today's summary to Telegram.

    Intended to be called by a daily scheduler. The scheduler authenticates the same way
    a browser does — POST /auth/login with credentials held as CI secrets, then send the
    bearer token — rather than through a separate shared key. One auth path means one
    thing to reason about when asking "who could have written this row".
    """
    today = await _build_today(db, calendar, day or date.today(), user)

    if not (today.todos or today.reminders_due or today.calendar_events):
        return Message(detail="Nothing due today; no notification sent")

    delivered = await telegram.send_message(_format_summary(today))
    return Message(
        detail="Notification sent" if delivered else "Notification could not be delivered"
    )


def _format_summary(today: TodayOut) -> str:
    """Render a Telegram HTML message.

    Note the escaping: titles are user-supplied and parse_mode is HTML, so an item
    called "<b>rent" would otherwise corrupt the message or be rejected by Telegram.
    """
    from html import escape

    lines = [f"<b>{today.date:%A, %d %B %Y}</b>"]

    if today.reminders_due:
        lines.append("\n<b>Reminders</b>")
        lines += [f"• {escape(r.title)}" for r in today.reminders_due]

    if today.todos:
        lines.append("\n<b>Todos</b>")
        lines += [f"• {escape(t.title)}" for t in today.todos]

    if today.calendar_events:
        lines.append("\n<b>Calendar</b>")
        lines += [f"• {escape(e.title)}" for e in today.calendar_events]

    return "\n".join(lines)
