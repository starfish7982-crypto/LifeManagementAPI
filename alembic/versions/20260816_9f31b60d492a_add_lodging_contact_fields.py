"""add lodging contact fields

Revision ID: 9f31b60d492a
Revises: f6a19e2d87bc
Create Date: 2026-08-16 17:32:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f31b60d492a"
down_revision: str | None = "f6a19e2d87bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("lodgings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("address", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("confirmation_number", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lodgings", schema=None) as batch_op:
        batch_op.drop_column("phone")
        batch_op.drop_column("confirmation_number")
        batch_op.drop_column("address")
