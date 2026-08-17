"""add todo lanes and order

Revision ID: 8c92a130d765
Revises: 7d99ad63143d
Create Date: 2026-08-16 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c92a130d765"
down_revision: str | None = "7d99ad63143d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("bucket", sa.String(length=10), nullable=False, server_default="today")
        )
        batch_op.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_check_constraint("ck_todo_bucket", "bucket IN ('today', 'later')")
        batch_op.create_index(
            "ix_todos_user_bucket_position", ["user_id", "bucket", "position"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_index("ix_todos_user_bucket_position")
        batch_op.drop_constraint("ck_todo_bucket", type_="check")
        batch_op.drop_column("position")
        batch_op.drop_column("bucket")
