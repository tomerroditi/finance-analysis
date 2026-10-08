"""restate the savings-goal ledger: income-funded goals take their waterfall turn

Revision ID: 926a3d40c807
Revises: 70538fb612c9
Create Date: 2026-10-08 12:00:00.000000

Goals filled by an income of their own (a "saved into" rule, or an investment
goal's funding income) now take part in the waterfall: surplus fills what their
income has not, and gives way once the income arrives. The rows the previous
rules wrote no longer add up, so, as in ``6950d212e44e``, the open goals'
ledger is cleared and recomputed on the next read. It is derived data only;
closed goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "926a3d40c807"
down_revision: str | Sequence[str] | None = "70538fb612c9"
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
