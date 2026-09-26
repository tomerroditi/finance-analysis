"""restate the savings-goal ledger: income-funded goals hold only their income

Revision ID: 6950d212e44e
Revises: 1f504bcccd13
Create Date: 2026-09-27 18:00:00.000000

A goal with a "saved into" rule no longer takes surplus from the waterfall and
is never clawed back, so the rows the previous rules wrote for it — and the
clawbacks that landed on other goals in its place — no longer add up. As in
``1f504bcccd13``, the open goals' ledger is cleared and recomputed on the next
read. It is derived data only; closed goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6950d212e44e"
down_revision: str | Sequence[str] | None = "1f504bcccd13"
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
