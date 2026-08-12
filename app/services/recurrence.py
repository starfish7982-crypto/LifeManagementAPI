"""Reminder recurrence maths.

Pulled out of the route handlers into a pure function of (reminder, today) so it can
be tested without a database or an HTTP client. Every awkward calendar case lives here.
"""

from __future__ import annotations

import calendar
from datetime import date

from app.models import Frequency, Reminder


def _clamp_day(year: int, month: int, day: int) -> date:
    """Return `day` in the given month, or the last valid day if it overflows.

    A reminder set for the 31st must still fire in February. Clamping (rather than
    skipping or rolling into March) is the behaviour people expect from "end of month".
    """
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def next_due(reminder: Reminder, today: date) -> date | None:
    """The next date this reminder fires, on or after `today`. None if it never will."""
    if not reminder.active:
        return None

    if reminder.frequency == Frequency.ONCE:
        # A past one-time reminder is done; it does not roll forward.
        if reminder.on_date is None or reminder.on_date < today:
            return None
        return reminder.on_date

    if reminder.frequency == Frequency.MONTHLY:
        assert reminder.day_of_month is not None
        candidate = _clamp_day(today.year, today.month, reminder.day_of_month)
        if candidate >= today:
            return candidate
        # Roll to next month, handling the December -> January year bump.
        year = today.year + (today.month // 12)
        month = today.month % 12 + 1
        return _clamp_day(year, month, reminder.day_of_month)

    if reminder.frequency == Frequency.YEARLY:
        assert reminder.day_of_month is not None and reminder.month_of_year is not None
        candidate = _clamp_day(today.year, reminder.month_of_year, reminder.day_of_month)
        if candidate >= today:
            return candidate
        # Feb 29 on a non-leap year clamps to Feb 28 via _clamp_day.
        return _clamp_day(today.year + 1, reminder.month_of_year, reminder.day_of_month)

    return None


def days_until_due(reminder: Reminder, today: date) -> int | None:
    due = next_due(reminder, today)
    return None if due is None else (due - today).days
