"""add travel expenses and receipt images

Revision ID: c31d0a8f9954
Revises: 2a7c5e6b1f43
Create Date: 2026-08-16 21:42:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c31d0a8f9954"
down_revision: str | None = "2a7c5e6b1f43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The local app uses create_all at boot for a fresh SQLite file. When a reload
    # sees the new ORM class before Alembic is run, the table can already exist; that
    # is a valid schema, not a reason to fail the first migration command.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("travel_expenses"):
        op.create_table(
            "travel_expenses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("trip_id", sa.Integer(), nullable=False),
            sa.Column("merchant", sa.String(length=200), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("spent_at", sa.Date(), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("receipt_filename", sa.String(length=255), nullable=True),
            sa.Column("receipt_media_type", sa.String(length=100), nullable=True),
            sa.Column("receipt_data", sa.LargeBinary(), nullable=True),
            sa.Column("ocr_text", sa.String(length=12000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)
    if "ix_travel_expenses_trip_date" not in {index["name"] for index in inspector.get_indexes("travel_expenses")}:
        op.create_index("ix_travel_expenses_trip_date", "travel_expenses", ["trip_id", "spent_at"])


def downgrade() -> None:
    op.drop_index("ix_travel_expenses_trip_date", table_name="travel_expenses")
    op.drop_table("travel_expenses")
