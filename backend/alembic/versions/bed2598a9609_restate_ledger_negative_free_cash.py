"""restate the savings-goal ledger: free cash may go negative

Revision ID: bed2598a9609
Revises: 5741e10f9f9a
Create Date: 2026-10-09 12:00:00.000000

An overspend no goal can give back no longer floors the free-cash pool, a
later surplus repays the hole before funding any goal, and a hole carried from
an earlier month never claws back again. The clawback rows the old floor
produced no longer add up, so, as in ``5741e10f9f9a``, the open goals' ledger
is cleared and recomputed on the next read. It is derived data only; closed
goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bed2598a9609"
down_revision: str | Sequence[str] | None = "5741e10f9f9a"
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
