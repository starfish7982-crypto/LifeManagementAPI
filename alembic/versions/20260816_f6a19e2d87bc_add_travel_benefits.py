"""add travel benefits

Revision ID: f6a19e2d87bc
Revises: c4d71f5ca082
Create Date: 2026-08-16 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a19e2d87bc"
down_revision: str | None = "c4d71f5ca082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "travel_benefits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_name", sa.String(length=200), nullable=False),
        sa.Column("benefit", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("travel_benefits", schema=None) as batch_op:
        batch_op.create_index(
            "ix_travel_benefits_user_expiry", ["user_id", "expires_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("travel_benefits", schema=None) as batch_op:
        batch_op.drop_index("ix_travel_benefits_user_expiry")
    op.drop_table("travel_benefits")
