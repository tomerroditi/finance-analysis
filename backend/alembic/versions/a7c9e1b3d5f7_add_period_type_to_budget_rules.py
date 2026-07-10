"""add period_type to budget_rules

Revision ID: a7c9e1b3d5f7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c9e1b3d5f7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add period_type discriminator and backfill from year/month null-ness.

    Idempotent: fresh DBs already have the column from
    ``Base.metadata.create_all``. Backfill classifies existing rows —
    ``month`` set ⇒ monthly, both ``year`` and ``month`` null ⇒ project.
    Yearly rows (year set, month null) do not exist before this feature.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "budget_rules" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("budget_rules")]
    if "period_type" not in columns:
        with op.batch_alter_table("budget_rules") as batch_op:
            batch_op.add_column(sa.Column("period_type", sa.String(), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE budget_rules SET period_type = 'monthly' "
            "WHERE month IS NOT NULL AND (period_type IS NULL OR period_type = '')"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE budget_rules SET period_type = 'project' "
            "WHERE month IS NULL AND year IS NULL "
            "AND (period_type IS NULL OR period_type = '')"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE budget_rules SET period_type = 'yearly' "
            "WHERE month IS NULL AND year IS NOT NULL "
            "AND (period_type IS NULL OR period_type = '')"
        )
    )


def downgrade() -> None:
    """Remove the period_type column."""
    with op.batch_alter_table("budget_rules") as batch_op:
        batch_op.drop_column("period_type")
