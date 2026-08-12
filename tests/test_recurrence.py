"""Recurrence is pure logic, so it is tested directly rather than through HTTP.

These are the cases that break naive implementations.
"""

from datetime import date

import pytest

from app.models import Frequency, Reminder
from app.services.recurrence import next_due


def make(frequency, **kwargs) -> Reminder:
    return Reminder(title="t", frequency=frequency, active=kwargs.pop("active", True), **kwargs)


def test_monthly_before_the_day_this_month():
    r = make(Frequency.MONTHLY, day_of_month=15)
    assert next_due(r, date(2026, 3, 1)) == date(2026, 3, 15)


def test_monthly_on_the_day_is_due_today():
    r = make(Frequency.MONTHLY, day_of_month=15)
    assert next_due(r, date(2026, 3, 15)) == date(2026, 3, 15)


def test_monthly_after_the_day_rolls_to_next_month():
    r = make(Frequency.MONTHLY, day_of_month=15)
    assert next_due(r, date(2026, 3, 16)) == date(2026, 4, 15)


def test_monthly_31st_clamps_in_february():
    r = make(Frequency.MONTHLY, day_of_month=31)
    assert next_due(r, date(2026, 2, 1)) == date(2026, 2, 28)


def test_monthly_31st_clamps_in_leap_february():
    r = make(Frequency.MONTHLY, day_of_month=31)
    assert next_due(r, date(2028, 2, 1)) == date(2028, 2, 29)


def test_monthly_rolls_across_the_year_boundary():
    r = make(Frequency.MONTHLY, day_of_month=5)
    assert next_due(r, date(2026, 12, 6)) == date(2027, 1, 5)


def test_yearly_this_year_then_next():
    r = make(Frequency.YEARLY, day_of_month=1, month_of_year=7)
    assert next_due(r, date(2026, 1, 1)) == date(2026, 7, 1)
    assert next_due(r, date(2026, 7, 2)) == date(2027, 7, 1)


def test_yearly_feb_29_clamps_on_non_leap_years():
    r = make(Frequency.YEARLY, day_of_month=29, month_of_year=2)
    assert next_due(r, date(2026, 3, 1)) == date(2027, 2, 28)


def test_once_in_the_future():
    r = make(Frequency.ONCE, on_date=date(2026, 5, 9))
    assert next_due(r, date(2026, 5, 1)) == date(2026, 5, 9)


def test_once_in_the_past_never_fires_again():
    r = make(Frequency.ONCE, on_date=date(2026, 5, 9))
    assert next_due(r, date(2026, 5, 10)) is None


def test_inactive_reminder_has_no_next_due():
    r = make(Frequency.MONTHLY, day_of_month=1, active=False)
    assert next_due(r, date(2026, 3, 5)) is None


@pytest.mark.parametrize("today", [date(2026, 1, 31), date(2026, 4, 30), date(2026, 12, 31)])
def test_monthly_last_day_is_stable_across_month_lengths(today):
    r = make(Frequency.MONTHLY, day_of_month=31)
    due = next_due(r, today)
    assert due is not None and due >= today
