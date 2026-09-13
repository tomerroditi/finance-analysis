"""add is_closed to budget_rules

Revision ID: e3b5d7f9a1c2
Revises: d4e6f8a0b2c4
Create Date: 2026-09-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3b5d7f9a1c2"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a0b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the ``is_closed`` flag project rules carry, defaulting to open.

    Idempotent: fresh DBs already have the column from
    ``Base.metadata.create_all``. Existing rows are backfilled to ``0`` so a
    project that predates the feature reads as open rather than as ``NULL``,
    which no caller should have to special-case.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "budget_rules" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("budget_rules")]
    if "is_closed" not in columns:
        with op.batch_alter_table("budget_rules") as batch_op:
            batch_op.add_column(
                sa.Column("is_closed", sa.Integer(), nullable=True, server_default="0")
            )

    conn.execute(sa.text("UPDATE budget_rules SET is_closed = 0 WHERE is_closed IS NULL"))


def downgrade() -> None:
    """Remove the is_closed column."""
    with op.batch_alter_table("budget_rules") as batch_op:
        batch_op.drop_column("is_closed")
