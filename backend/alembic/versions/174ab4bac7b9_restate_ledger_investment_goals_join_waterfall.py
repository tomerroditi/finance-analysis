"""restate the savings-goal ledger: every investment goal takes its waterfall turn

Revision ID: 174ab4bac7b9
Revises: 926a3d40c807
Create Date: 2026-10-08 14:00:00.000000

Every investment goal now takes surplus in its waterfall turn as cash waiting
to be invested, and a goal with income of its own takes surplus only for what
that income will never cover. The rows the previous rules wrote no longer add
up, so, as in ``926a3d40c807``, the open goals' ledger is cleared and
recomputed on the next read. It is derived data only; closed goals keep their
frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "174ab4bac7b9"
down_revision: str | Sequence[str] | None = "926a3d40c807"
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
