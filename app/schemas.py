"""Pydantic request/response models.

These are deliberately separate from the ORM models. The ORM describes how data is
stored; these describe the API contract. Keeping them apart means a column rename does
not silently become a breaking API change, and clients cannot write to fields (id,
created_at) that the server owns.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Frequency

# ----------------------------------------------------------------------------- auth


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    # 8 is the floor, not the goal. A length minimum is the only password rule worth
    # enforcing: composition rules ("one symbol, one digit") measurably push people
    # toward predictable substitutions without adding entropy. 200 caps the work an
    # unauthenticated caller can make the Argon2 hasher do.
    password: str = Field(min_length=8, max_length=200)

    @field_validator("username")
    @classmethod
    def normalise(cls, v: str) -> str:
        # Stored lowercase so that Sally and sally cannot become two accounts.
        return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    created_at: datetime


class PasswordChange(BaseModel):
    # The current password is required even though the caller already holds a valid
    # token. A token can be a borrowed laptop or a stolen localStorage entry; asking
    # for the password is what stops that from becoming permanent ownership of the
    # account. It is the reason this is not just `new_password`.
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class Token(BaseModel):
    access_token: str
    # OAuth2 bearer responses are specified to carry this field; /docs reads it.
    token_type: str = "bearer"
    expires_in: int


class AuthConfig(BaseModel):
    """Read by the sign-in screen before authentication, to decide what to render."""

    registration_open: bool


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
    category: str | None = Field(default=None, max_length=60)
    purpose: str = Field(min_length=1, max_length=200)
    next_step: str | None = Field(default=None, max_length=200)


class AssetGoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    amount: Decimal
    category: str | None
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


class ReorderIn(BaseModel):
    """Every row of the list, in the order they should end up.

    The whole set rather than a "move row 3 to position 7" instruction. A partial
    update has to define what happens to the rows it did not mention, and every answer
    to that is a rule the client has to know too; sending the full order means the
    request says exactly what the result should be. It also makes the operation
    idempotent — replaying it changes nothing — which matters when the network is what
    decides whether it arrives twice.
    """

    ids: list[int] = Field(min_length=1, max_length=1000)


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
    bucket: Literal["today", "later"] = "today"


class TodoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    done: bool | None = None
    bucket: Literal["today", "later"] | None = None


class TodoOrderIn(BaseModel):
    """The complete order of one lane, so the requested result is unambiguous."""

    bucket: Literal["today", "later"]
    ids: list[int] = Field(min_length=0, max_length=500)


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    due_date: date | None
    done: bool
    bucket: Literal["today", "later"]
    position: int
    source: str
    calendar_time: time | None = None
    created_at: datetime


# --------------------------------------------------------------------------- ideas


class IdeaIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    note: str | None
    created_at: datetime


# ------------------------------------------------------------------------- grocery


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ingredients: str | None = Field(default=None, max_length=2000)
    steps: str | None = Field(default=None, max_length=4000)
    temp: str | None = Field(default=None, max_length=100)
    video_url: str | None = Field(default=None, max_length=500)

    @field_validator("video_url")
    @classmethod
    def only_web_links(cls, v: str | None) -> str | None:
        """Reject anything that is not http(s).

        The field is rendered as a link the user clicks. `javascript:` in an href is
        script execution on this origin, which is the one thing that would make the
        access token in localStorage readable. React escapes text, not URLs — this is
        the gap it does not close for you.
        """
        if v is None or not v.strip():
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("video_url must start with http:// or https://")
        return v


class RecipeOut(RecipeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class MealIdeaIn(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=50)


class MealIdeaOut(MealIdeaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ShoppingItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=100)
    done: bool = False


class ShoppingItemPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=100)
    done: bool | None = None


class ShoppingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    quantity: str | None
    done: bool
    position: int


# -------------------------------------------------------------------------- travel


class LodgingIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    check_in: date | None = None
    check_out: date | None = None
    address: str | None = Field(default=None, max_length=500)
    confirmation_number: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=80)
    details: str | None = Field(default=None, max_length=500)


class LodgingOut(LodgingIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PackingItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    done: bool = False


class PackingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    done: bool
    position: int


class TravelExpenseIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    spent_at: date
    category: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class TravelExpenseOut(TravelExpenseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    has_receipt: bool
    receipt_filename: str | None
    ocr_text: str | None


class TravelBenefitIn(BaseModel):
    card_name: str = Field(min_length=1, max_length=200)
    benefit: str | None = Field(default=None, max_length=1000)
    expires_at: date | None = None


class TravelBenefitOut(TravelBenefitIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CalendarLodgingSuggestion(BaseModel):
    """A likely hotel stay derived from the caller's cached calendar feed."""

    name: str
    check_in: date | None = None
    check_out: date | None = None
    address: str | None = None
    confirmation_number: str | None = None
    phone: str | None = None
    details: str | None = None


class TripIn(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    license_plate: str | None = Field(default=None, max_length=32)

    def model_post_init(self, __context) -> None:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    start_date: date | None
    end_date: date | None
    license_plate: str | None
    updated_at: datetime
    lodgings: list[LodgingOut]
    packing: list[PackingItemOut]
    expenses: list[TravelExpenseOut]


# ------------------------------------------------------------------------ settings


class UserSettingsIn(BaseModel):
    telegram_bot_token: str | None = Field(default=None, max_length=200)
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    google_calendar_ical_url: str | None = Field(default=None, max_length=500)

    @field_validator("google_calendar_ical_url")
    @classmethod
    def only_web_links(cls, v: str | None) -> str | None:
        # The server fetches this URL. Without a scheme check, `file:///etc/passwd`
        # would be a request to read the container's filesystem through the API.
        if v is None or not v.strip():
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("google_calendar_ical_url must start with http:// or https://")
        return v


class UserSettingsOut(BaseModel):
    """What the settings screen may see.

    The bot token is never returned — only whether one is set. A secret that has been
    written should not be readable back: the screen needs to show "configured", not the
    value, and anything that returns it puts it in a response, a browser cache, and any
    log that records bodies.
    """

    telegram_configured: bool
    telegram_chat_id: str | None
    google_calendar_ical_url: str | None
    updated_at: datetime | None


class CalendarEvent(BaseModel):
    uid: str | None = None
    title: str
    starts_at: date
    starts_time: time | None = None
    ends_at: date | None = None
    all_day: bool
    description: str | None = None
    location: str | None = None


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
