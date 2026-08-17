"""add calendar todo key

Revision ID: 4e52b915c40e
Revises: 9f31b60d492a
Create Date: 2026-08-16 18:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e52b915c40e"
down_revision: str | None = "9f31b60d492a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("calendar_event_key", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_todo_user_calendar_event", ["user_id", "calendar_event_key"])


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_constraint("uq_todo_user_calendar_event", type_="unique")
        batch_op.drop_column("calendar_event_key")
