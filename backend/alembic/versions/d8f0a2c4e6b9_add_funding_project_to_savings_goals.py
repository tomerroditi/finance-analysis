"""add funding_project to savings_goals

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


def upgrade() -> None:
    """Add the column naming the project budget a goal pays for."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "savings_goals" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("savings_goals")]
    if "funding_project" not in columns:
        with op.batch_alter_table("savings_goals") as batch_op:
            batch_op.add_column(
                sa.Column("funding_project", sa.String(), nullable=True)
            )


def downgrade() -> None:
    """Remove the funding_project column from savings_goals."""
    with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
        batch_op.drop_column("funding_project")
