"""add per-person packing lists

Revision ID: 87fd42d6e2ba
Revises: 56db8b47e7ac
Create Date: 2026-08-19 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "87fd42d6e2ba"
down_revision: str | None = "56db8b47e7ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    # `Base.metadata.create_all()` is used by the test/first-run SQLite setup.  It can
    # create the new table before this revision is stamped, so the migration needs to
    # be safe in either order while still migrating the existing packing rows.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("packing_lists"):
        op.create_table(
            "packing_lists",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("trip_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_packing_lists_trip_position", "packing_lists", ["trip_id", "position"])

    # Every existing trip gets a default list, so no current packing item is lost.
    op.execute(
        "INSERT INTO packing_lists (trip_id, name, position) "
        "SELECT id, '出門 Checklist', 0 FROM trips "
        "WHERE NOT EXISTS (SELECT 1 FROM packing_lists WHERE packing_lists.trip_id = trips.id)"
    )

    packing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("packing_items")}
    if "packing_list_id" not in packing_columns:
        with op.batch_alter_table("packing_items", schema=None) as batch_op:
            batch_op.add_column(sa.Column("packing_list_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE packing_items SET packing_list_id = (SELECT id FROM packing_lists "
        "WHERE packing_lists.trip_id = packing_items.trip_id ORDER BY id LIMIT 1) "
        "WHERE packing_list_id IS NULL"
    )
    packing_column = next(
        column for column in sa.inspect(op.get_bind()).get_columns("packing_items")
        if column["name"] == "packing_list_id"
    )
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("packing_items")
    has_packing_list_fk = any(
        foreign_key.get("referred_table") == "packing_lists" for foreign_key in foreign_keys
    )
    if packing_column["nullable"] or not has_packing_list_fk:
        with op.batch_alter_table("packing_items", schema=None) as batch_op:
            if packing_column["nullable"]:
                batch_op.alter_column("packing_list_id", existing_type=sa.Integer(), nullable=False)
            if not has_packing_list_fk:
                batch_op.create_foreign_key(
                    "fk_packing_items_packing_list",
                    "packing_lists",
                    ["packing_list_id"],
                    ["id"],
                    ondelete="CASCADE",
                )


def downgrade() -> None:
    with op.batch_alter_table("packing_items", schema=None) as batch_op:
        batch_op.drop_constraint("fk_packing_items_packing_list", type_="foreignkey")
        batch_op.drop_column("packing_list_id")
    op.drop_index("ix_packing_lists_trip_position", table_name="packing_lists")
    op.drop_table("packing_lists")
