"""SQLAlchemy ORM models.

Schema shape and why:

  AssetSnapshot 1---* AssetItem
      A snapshot is one month's picture of net worth; items are the individual
      accounts or holdings inside it. Splitting them (rather than storing a JSON
      blob per month) is what makes "total by category across time" a single
      GROUP BY instead of application-side aggregation.

  Reminder
      Recurring (monthly/yearly) or one-time. `next_due` is computed in Python
      rather than stored, so changing the recurrence rule cannot leave a stale
      denormalised date behind.

  Todo
      Flat list with a due date and a done flag.

  ListTable 1---* ListItem
      User-defined tables: the columns are a JSON array of headings, and each row holds
      a positional array of values. This is the generic half of the app — subscriptions,
      warranties, budgets — where the shape is whatever the owner decides.

  AssetGoal
      One savings target per user, so the dashboard can show progress toward it.

  User 1---* everything above
      Every row belongs to exactly one user. The ownership column is NOT NULL with an
      ON DELETE CASCADE foreign key, so orphaned rows are impossible and deleting an
      account really deletes the account's data. Scoping is enforced in every query
      rather than by convention; see `app/routers/` for the single helper each router
      uses to build a user-scoped SELECT.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Frequency(str, Enum):
    """str-mixin Enum rather than StrEnum: StrEnum is 3.11+, and this keeps 3.10 support."""

    ONCE = "once"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Citext would be tidier on Postgres, but it is an extension and SQLite has no
    # equivalent. Normalising to lowercase before insert keeps one behaviour on both.
    username: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    # Argon2id output, never the password. Length is generous: the encoded form carries
    # the algorithm, parameters and salt alongside the digest, and those parameters are
    # expected to grow as hardware does.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Stored as the first day of the month it represents.
    month: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    items: Mapped[list[AssetItem]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        # One snapshot per month *per user*. The constraint was UNIQUE(month) before
        # accounts existed; leaving it that way would have meant the second user on the
        # system could not record March because the first user already had.
        UniqueConstraint("user_id", "month", name="uq_snapshot_user_month"),
    )

    @property
    def total(self) -> Decimal:
        # Kept as Decimal deliberately. Casting to float here would undo the reason
        # the column is Numeric(14, 2) in the first place.
        return sum((item.amount for item in self.items), Decimal("0"))


class AssetItem(Base):
    __tablename__ = "asset_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("asset_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    # Numeric, not Float: money in binary floating point accumulates rounding error.
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    snapshot: Mapped[AssetSnapshot] = relationship(back_populates="items")

    __table_args__ = (
        # The dashboard groups by category within a snapshot; this index serves it.
        Index("ix_asset_items_snapshot_category", "snapshot_id", "category"),
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    # For MONTHLY: 1-31. For YEARLY/ONCE: unused (ONCE uses `on_date`).
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    month_of_year: Mapped[int | None] = mapped_column(Integer)
    on_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Lead time: how many days before the due date this should start showing up. The
    # tax reminder is the motivating case — knowing on April 1st that filing is due on
    # the 15th is useful; being told on the 15th is not.
    days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "frequency IN ('once', 'monthly', 'yearly')", name="ck_reminder_frequency"
        ),
        CheckConstraint(
            "day_of_month IS NULL OR (day_of_month BETWEEN 1 AND 31)",
            name="ck_reminder_day_of_month",
        ),
        CheckConstraint(
            "month_of_year IS NULL OR (month_of_year BETWEEN 1 AND 12)",
            name="ck_reminder_month_of_year",
        ),
        CheckConstraint(
            "days_before BETWEEN 0 AND 365", name="ck_reminder_days_before"
        ),
        # Every listing filters by owner first, then by active. Leading the index with
        # user_id is what makes it usable for that access pattern.
        Index("ix_reminders_user_active", "user_id", "active"),
    )


class AssetGoal(Base):
    """A savings target, at most one per user.

    Uniqueness is on user_id alone: "the goal" is singular in the UI, and enforcing that
    in the database means the API cannot accidentally end up with two and have to pick.
    """

    __tablename__ = "asset_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # The asset category used for progress (e.g. Checking & Saving).  It is separate
    # from the human goal description shown in the dashboard.
    category: Mapped[str | None] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    next_step: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ListTable(Base):
    """A user-defined table: a name, an ordered set of column headings, and rows.

    Named ListTable rather than List because `list` is a builtin and `List` is a typing
    import; a model class that shadows either is a readability trap in every file that
    touches it.

    The columns live as a JSON array of strings rather than as their own table. The
    alternative — a columns table plus an EAV values table — buys per-column types and
    constraints, which this feature does not have: every cell here is free text typed by
    the person who owns the row. It would cost a three-way join to render one screen.
    """

    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16))
    columns: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    # Explicit display order. Without it the UI would be at the mercy of whatever order
    # the database returned rows in, which is not guaranteed to be stable.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    items: Mapped[list[ListItem]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ListItem.position",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_list_user_name"),
        Index("ix_lists_user_position", "user_id", "position"),
    )


class ListItem(Base):
    """One row. `values` is positional: values[i] belongs under columns[i].

    Keeping them aligned is the API's job, not the database's — no SQL constraint can
    express "this array is as long as that array on the parent". `app/routers/lists.py`
    validates it on every write, and there is a test for the mismatch.
    """

    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("lists.id", ondelete="CASCADE"), nullable=False
    )
    values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    table: Mapped[ListTable] = relationship(back_populates="items")

    __table_args__ = (Index("ix_list_items_list_position", "list_id", "position"),)


class UserSettings(Base):
    """Per-user integration credentials, one row per account.

    These lived as server-wide environment variables until accounts existed, which
    quietly made them everyone's: a second user calling /today saw the first user's
    calendar, because there was only ever one iCal URL. Moving them here is what makes
    the integrations follow the account like the rest of the data does.

    The Telegram bot token is a credential, stored in plaintext. That is the same
    exposure as DATABASE_URL — anyone who can read the database can read it — and the
    honest mitigation is that it grants only the ability to post to one chat. A service
    holding tokens for many people would want them encrypted with a key the database
    does not have; noted in the README rather than half-built here.
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    telegram_bot_token: Mapped[str | None] = mapped_column(String(200))
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    google_calendar_ical_url: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_ideas_user_created", "user_id", "created_at"),)


class Recipe(Base):
    """Free text throughout. Ingredients are one string rather than a related table
    because nothing here ever queries them — the screen shows them, and that is all.
    A shopping list generated from a recipe would change that answer."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ingredients: Mapped[str | None] = mapped_column(String(2000))
    steps: Mapped[str | None] = mapped_column(String(4000))
    temp: Mapped[str | None] = mapped_column(String(100))
    video_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_recipes_user_name", "user_id", "name"),)


class MealIdea(Base):
    """A compact menu backlog, separate from full recipes.

    A recipe carries ingredients and method; an idea only answers "what could we
    cook?". Keeping the two collections distinct avoids creating fake, empty recipes
    just to record a meal name and its status.
    """

    __tablename__ = "meal_ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="常做")

    __table_args__ = (Index("ix_meal_ideas_user_category_name", "user_id", "category", "name"),)


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(100))
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_shopping_user_position", "user_id", "position"),)


class Trip(Base):
    """One trip per user.

    A singleton, like AssetGoal, because that is what the screen shows: dates, a
    number plate, where you are staying, what to pack. Supporting several would be a
    `user_id` index instead of a unique constraint and a trip picker in the UI — worth
    doing the first time a second trip needs to exist at once, not before.
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    license_plate: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    lodgings: Mapped[list[Lodging]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Lodging.check_in",
    )
    packing: Mapped[list[PackingItem]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PackingItem.position",
    )
    expenses: Mapped[list[TravelExpense]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TravelExpense.spent_at.desc(), TravelExpense.id.desc()",
    )


class Lodging(Base):
    __tablename__ = "lodgings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    check_in: Mapped[date | None] = mapped_column(Date)
    check_out: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(String(500))
    confirmation_number: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(String(500))

    trip: Mapped[Trip] = relationship(back_populates="lodgings")


class PackingItem(Base):
    __tablename__ = "packing_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    trip: Mapped[Trip] = relationship(back_populates="packing")


class TravelExpense(Base):
    """A trip expense, optionally backed by the original receipt image.

    Keeping the image in the database makes access ownership-aware: it is never a
    public static file URL that another signed-in person could guess.
    """

    __tablename__ = "travel_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    merchant: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    spent_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    category: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(String(500))
    receipt_filename: Mapped[str | None] = mapped_column(String(255))
    receipt_media_type: Mapped[str | None] = mapped_column(String(100))
    receipt_data: Mapped[bytes | None] = mapped_column()
    ocr_text: Mapped[str | None] = mapped_column(String(12000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    trip: Mapped[Trip] = relationship(back_populates="expenses")

    @property
    def has_receipt(self) -> bool:
        return self.receipt_data is not None

    __table_args__ = (Index("ix_travel_expenses_trip_date", "trip_id", "spent_at"),)


class TravelBenefit(Base):
    """A credit-card travel benefit that is useful even between trips."""

    __tablename__ = "travel_benefits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    card_name: Mapped[str] = mapped_column(String(200), nullable=False)
    benefit: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (Index("ix_travel_benefits_user_expiry", "user_id", "expires_at"),)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # A task starts in today's lane.  Keeping lane and position on the record (rather
    # than only in React state) means a deliberate plan survives a reload and is the
    # same on every device the account uses.
    bucket: Mapped[str] = mapped_column(String(10), nullable=False, default="today")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # The Google UID plus occurrence date.  This lets an activity become a checkable
    # task exactly once without relying on its (editable, non-unique) title.
    calendar_event_key: Mapped[str | None] = mapped_column(String(255))
    calendar_time: Mapped[time | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("bucket IN ('today', 'later')", name="ck_todo_bucket"),
        UniqueConstraint("user_id", "calendar_event_key", name="uq_todo_user_calendar_event"),
        Index("ix_todos_user_due_done", "user_id", "due_date", "done"),
        Index("ix_todos_user_bucket_position", "user_id", "bucket", "position"),
    )
