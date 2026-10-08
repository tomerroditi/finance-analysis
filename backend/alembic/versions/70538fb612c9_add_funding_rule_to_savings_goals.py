"""add an investment goal's funding rule to savings_goals

Revision ID: 70538fb612c9
Revises: 6950d212e44e
Create Date: 2026-10-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70538fb612c9"
down_revision: str | Sequence[str] | None = "6950d212e44e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("funding_category", "funding_tags")


def upgrade() -> None:
    """Add the income an investment goal's transfers are paid from."""
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
    """Remove the funding rule columns."""
    with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
        for name in _COLUMNS:
            batch_op.drop_column(name)
