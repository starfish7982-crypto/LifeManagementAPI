"""add meal ideas

Revision ID: c4d71f5ca082
Revises: 8c92a130d765
Create Date: 2026-08-16 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d71f5ca082"
down_revision: str | None = "8c92a130d765"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_ideas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("meal_ideas", schema=None) as batch_op:
        batch_op.create_index(
            "ix_meal_ideas_user_category_name", ["user_id", "category", "name"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("meal_ideas", schema=None) as batch_op:
        batch_op.drop_index("ix_meal_ideas_user_category_name")
    op.drop_table("meal_ideas")
