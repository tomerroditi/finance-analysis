"""add refund_split_id to refund_links

Revision ID: e3c5a7b9d1f2
Revises: b7d9f1a3c5e2
Create Date: 2026-10-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3c5a7b9d1f2"
down_revision: str | Sequence[str] | None = "b7d9f1a3c5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Let a refund link name the split part of the refund it covers.

    Every existing link covers its whole refund transaction, which is what a
    null ``refund_split_id`` means, so no backfill is needed.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "refund_links" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("refund_links")}
    if "refund_split_id" not in existing:
        with op.batch_alter_table("refund_links") as batch_op:
            batch_op.add_column(
                sa.Column("refund_split_id", sa.Integer(), nullable=True)
            )


def downgrade() -> None:
    """Remove refund_split_id from refund_links."""
    with op.batch_alter_table("refund_links", recreate="always") as batch_op:
        batch_op.drop_column("refund_split_id")
