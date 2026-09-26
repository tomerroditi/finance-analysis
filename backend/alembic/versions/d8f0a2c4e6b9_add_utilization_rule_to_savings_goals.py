"""add utilization category and tags to savings_goals

Revision ID: d8f0a2c4e6b9
Revises: c6e8a0b2d4f7
Create Date: 2026-09-26 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f0a2c4e6b9"
down_revision: str | Sequence[str] | None = "c6e8a0b2d4f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("utilization_category", "utilization_tags")


def upgrade() -> None:
    """Add the category/tag rule naming the spending a goal pays for."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "savings_goals" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("savings_goals")}
    missing = [name for name in _COLUMNS if name not in existing]
    if missing:
        with op.batch_alter_table("savings_goals") as batch_op:
            for name in missing:
                batch_op.add_column(sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    """Remove the utilization rule columns from savings_goals."""
    with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
        for name in _COLUMNS:
            batch_op.drop_column(name)
