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

  User 1---* everything above
      Every row belongs to exactly one user. The ownership column is NOT NULL with an
      ON DELETE CASCADE foreign key, so orphaned rows are impossible and deleting an
      account really deletes the account's data. Scoping is enforced in every query
      rather than by convention; see `app/routers/` for the single helper each router
      uses to build a user-scoped SELECT.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
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
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
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


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_todos_user_due_done", "user_id", "due_date", "done"),)
