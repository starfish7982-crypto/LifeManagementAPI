"""use username for accounts

Revision ID: 56db8b47e7ac
Revises: c31d0a8f9954
Create Date: 2026-08-16 22:06:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "56db8b47e7ac"
down_revision: str | None = "c31d0a8f9954"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The existing value is retained and simply becomes the account name. Batch mode
    # works on SQLite, where renaming a constrained column requires rebuilding it.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "email",
            new_column_name="username",
            existing_type=sa.String(length=320),
            type_=sa.String(length=60),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "username",
            new_column_name="email",
            existing_type=sa.String(length=60),
            type_=sa.String(length=320),
            existing_nullable=False,
        )
