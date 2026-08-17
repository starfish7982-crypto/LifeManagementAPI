"""add calendar todo time

Revision ID: e8a24f8d6b12
Revises: 4e52b915c40e
Create Date: 2026-08-16 18:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8a24f8d6b12"
down_revision: str | None = "4e52b915c40e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("calendar_time", sa.Time(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_column("calendar_time")
