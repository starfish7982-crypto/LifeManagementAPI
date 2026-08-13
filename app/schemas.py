"""Pydantic request/response models.

These are deliberately separate from the ORM models. The ORM describes how data is
stored; these describe the API contract. Keeping them apart means a column rename does
not silently become a breaking API change, and clients cannot write to fields (id,
created_at) that the server owns.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import Frequency

# ----------------------------------------------------------------------------- auth


class UserCreate(BaseModel):
    email: EmailStr
    # 8 is the floor, not the goal. A length minimum is the only password rule worth
    # enforcing: composition rules ("one symbol, one digit") measurably push people
    # toward predictable substitutions without adding entropy. 200 caps the work an
    # unauthenticated caller can make the Argon2 hasher do.
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def normalise(cls, v: str) -> str:
        # Stored lowercase so that Sally@ and sally@ cannot become two accounts.
        return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    # OAuth2 bearer responses are specified to carry this field; /docs reads it.
    token_type: str = "bearer"
    expires_in: int


# --------------------------------------------------------------------------- assets


class AssetItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    amount: Decimal = Field(max_digits=14, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class AssetItemOut(AssetItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AssetSnapshotIn(BaseModel):
    month: date
    note: str | None = Field(default=None, max_length=500)
    items: list[AssetItemIn] = Field(default_factory=list)

    @field_validator("month")
    @classmethod
    def normalise_to_first_of_month(cls, v: date) -> date:
        # Callers may send any day; a snapshot identifies a month, so collapse it.
        # Without this, 2026-03-04 and 2026-03-28 would be two different snapshots
        # and the UNIQUE(month) constraint would not do what its name promises.
        return v.replace(day=1)


class AssetSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    month: date
    note: str | None
    created_at: datetime
    items: list[AssetItemOut]
    total: Decimal


class CategoryTotal(BaseModel):
    category: str
    total: Decimal


class AssetGoalIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    purpose: str = Field(min_length=1, max_length=200)
    next_step: str | None = Field(default=None, max_length=200)


class AssetGoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    amount: Decimal
    purpose: str
    next_step: str | None
    updated_at: datetime


# ---------------------------------------------------------------------------- lists


class ListItemIn(BaseModel):
    values: list[str] = Field(max_length=50)


class ListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    values: list[str]
    position: int


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=16)
    # At least one column: a table with no columns can hold no information, and every
    # row in it would have to be the empty array.
    columns: list[str] = Field(min_length=1, max_length=50)
    position: int = Field(default=0, ge=0)


class ListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    icon: str | None
    columns: list[str]
    position: int
    created_at: datetime
    items: list[ListItemOut]


# ------------------------------------------------------------------------ reminders


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    frequency: Frequency
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    month_of_year: int | None = Field(default=None, ge=1, le=12)
    on_date: date | None = None
    active: bool = True
    days_before: int = Field(default=0, ge=0, le=365)
    note: str | None = Field(default=None, max_length=500)

    def model_post_init(self, __context) -> None:
        # Cross-field rules cannot live on a single field validator.
        if self.frequency is Frequency.ONCE and self.on_date is None:
            raise ValueError("on_date is required when frequency is 'once'")
        if self.frequency is Frequency.MONTHLY and self.day_of_month is None:
            raise ValueError("day_of_month is required when frequency is 'monthly'")
        if self.frequency is Frequency.YEARLY and (
            self.day_of_month is None or self.month_of_year is None
        ):
            raise ValueError(
                "day_of_month and month_of_year are required when frequency is 'yearly'"
            )


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    frequency: Frequency
    day_of_month: int | None
    month_of_year: int | None
    on_date: date | None
    active: bool
    days_before: int
    note: str | None
    created_at: datetime
    next_due: date | None
    days_until_due: int | None


# ---------------------------------------------------------------------------- todos


class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    done: bool = False


class TodoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    done: bool | None = None


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    due_date: date | None
    done: bool
    source: str
    created_at: datetime


class CalendarEvent(BaseModel):
    title: str
    starts_at: date
    all_day: bool


class TodayOut(BaseModel):
    date: date
    todos: list[TodoOut]
    reminders_due: list[ReminderOut]
    calendar_events: list[CalendarEvent]


# --------------------------------------------------------------------------- shared


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class Message(BaseModel):
    detail: str
