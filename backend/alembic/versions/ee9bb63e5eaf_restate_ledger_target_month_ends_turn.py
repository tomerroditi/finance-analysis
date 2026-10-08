"""restate the savings-goal ledger: a goal's turn ends at its target month

Revision ID: ee9bb63e5eaf
Revises: bed2598a9609
Create Date: 2026-10-09 14:00:00.000000

A goal with a target date now takes new money only up to that month, so the
rows that let a past goal keep soaking up every later surplus no longer add
up. As in ``bed2598a9609``, the open goals' ledger is cleared and recomputed on
the next read. It is derived data only; closed goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ee9bb63e5eaf"
down_revision: str | Sequence[str] | None = "bed2598a9609"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Clear the open goals' allocation rows so they are recomputed."""
    conn = op.get_bind()
    tables = sa.inspect(conn).get_table_names()
    if "savings_goal_allocations" not in tables or "savings_goals" not in tables:
        return
    conn.execute(
        sa.text(
            "DELETE FROM savings_goal_allocations WHERE goal_id IN "
            "(SELECT id FROM savings_goals WHERE status != 'closed')"
        )
    )


def downgrade() -> None:
    """Nothing to restore: the ledger is recomputed from transactions."""
