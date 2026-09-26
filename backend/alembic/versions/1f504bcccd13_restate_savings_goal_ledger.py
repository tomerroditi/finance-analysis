"""restate the savings-goal ledger under rule-funded goals

Revision ID: 1f504bcccd13
Revises: b9a0f25d4d28
Create Date: 2026-09-27 12:00:00.000000

A goal with a "saved into" rule now borrows surplus until its own income
lands and hands it back after, and a bill a goal cannot cover is paid out of
free cash. Rows written under the old rules no longer add up under the new
ones, so the open goals' ledger is cleared and the engine recomputes it on
the next read — the same thing an explicit rebuild does. It is derived data
only. Closed goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f504bcccd13"
down_revision: str | Sequence[str] | None = "b9a0f25d4d28"
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
