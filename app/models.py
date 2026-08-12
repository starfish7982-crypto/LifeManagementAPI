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


class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored as the first day of the month it represents.
    month: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    items: Mapped[list[AssetItem]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # One snapshot per month. Enforced by the database, not just by the API layer,
    # so a second writer (a script, a migration) cannot violate it.
    __table_args__ = (UniqueConstraint("month", name="uq_snapshot_month"),)

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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    # For MONTHLY: 1-31. For YEARLY/ONCE: unused (ONCE uses `on_date`).
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    month_of_year: Mapped[int | None] = mapped_column(Integer)
    on_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
        Index("ix_reminders_active", "active"),
    )


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_todos_due_done", "due_date", "done"),)
