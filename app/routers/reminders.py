"""Reminder endpoints. `next_due` and `days_until_due` are computed per request."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Reminder
from app.schemas import ReminderIn, ReminderOut
from app.security import require_api_key
from app.services.recurrence import days_until_due, next_due

router = APIRouter(
    prefix="/reminders",
    tags=["reminders"],
    dependencies=[Depends(require_api_key)],
)


def _to_out(reminder: Reminder, today: date) -> ReminderOut:
    return ReminderOut(
        id=reminder.id,
        title=reminder.title,
        frequency=reminder.frequency,
        day_of_month=reminder.day_of_month,
        month_of_year=reminder.month_of_year,
        on_date=reminder.on_date,
        active=reminder.active,
        created_at=reminder.created_at,
        next_due=next_due(reminder, today),
        days_until_due=days_until_due(reminder, today),
    )


def _get_or_404(db: Session, reminder_id: int) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    return reminder


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
    due_within_days: int | None = Query(None, ge=0, le=365),
    today: date | None = Query(None, description="Override 'today'; used by tests"),
) -> list[ReminderOut]:
    reference = today or date.today()

    stmt = select(Reminder)
    if active_only:
        stmt = stmt.where(Reminder.active.is_(True))

    results = [_to_out(r, reference) for r in db.scalars(stmt)]

    if due_within_days is not None:
        # Filtered in Python because next_due is derived, not stored. That is a real
        # trade-off: it costs a full scan. It is the right call at personal-data scale,
        # and the fix if it ever isn't would be a materialised next_due column kept
        # current by a trigger or a nightly job.
        results = [
            r
            for r in results
            if r.days_until_due is not None and r.days_until_due <= due_within_days
        ]

    results.sort(key=lambda r: (r.days_until_due is None, r.days_until_due))
    return results


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(payload: ReminderIn, db: Session = Depends(get_db)) -> ReminderOut:
    reminder = Reminder(**payload.model_dump())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _to_out(reminder, date.today())


@router.get("/{reminder_id}", response_model=ReminderOut)
def get_reminder(reminder_id: int, db: Session = Depends(get_db)) -> ReminderOut:
    return _to_out(_get_or_404(db, reminder_id), date.today())


@router.put("/{reminder_id}", response_model=ReminderOut)
def replace_reminder(
    reminder_id: int, payload: ReminderIn, db: Session = Depends(get_db)
) -> ReminderOut:
    reminder = _get_or_404(db, reminder_id)
    for field, value in payload.model_dump().items():
        setattr(reminder, field, value)
    db.commit()
    db.refresh(reminder)
    return _to_out(reminder, date.today())


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_get_or_404(db, reminder_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
