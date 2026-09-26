"""add kind to savings_goals

Revision ID: 395a5712d6e3
Revises: d8f0a2c4e6b9
Create Date: 2026-09-26 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "395a5712d6e3"
down_revision: str | Sequence[str] | None = "d8f0a2c4e6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the goal kind; every existing goal is a cash goal."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "savings_goals" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("savings_goals")}
    if "kind" not in existing:
        with op.batch_alter_table("savings_goals") as batch_op:
            batch_op.add_column(
                sa.Column("kind", sa.String(), nullable=True, server_default="cash")
            )


def downgrade() -> None:
    """Remove the goal kind from savings_goals."""
    with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
        batch_op.drop_column("kind")
