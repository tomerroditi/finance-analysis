"""add fire_scenarios table

Revision ID: b7d9f1a3c5e2
Revises: 70538fb612c9
Create Date: 2026-10-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d9f1a3c5e2"
down_revision: str | Sequence[str] | None = "70538fb612c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table holding the saved early-retirement plan.

    Idempotent: a fresh DB already has the table from
    ``Base.metadata.create_all``. No backfill — until the user saves a plan,
    one is derived from their tracked data and their old retirement goal.
    """
    conn = op.get_bind()
    if "fire_scenarios" in sa.inspect(conn).get_table_names():
        return

    op.create_table(
        "fire_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fields", sa.Text(), nullable=False),
        sa.Column("linked", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Drop the fire_scenarios table."""
    op.drop_table("fire_scenarios")
