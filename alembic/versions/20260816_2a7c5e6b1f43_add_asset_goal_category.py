"""add asset goal category

Revision ID: 2a7c5e6b1f43
Revises: e8a24f8d6b12
Create Date: 2026-08-16 21:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2a7c5e6b1f43"
down_revision: str | None = "e8a24f8d6b12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("asset_goals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=60), nullable=True))
    op.execute("UPDATE asset_goals SET category = purpose WHERE category IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("asset_goals", schema=None) as batch_op:
        batch_op.drop_column("category")
