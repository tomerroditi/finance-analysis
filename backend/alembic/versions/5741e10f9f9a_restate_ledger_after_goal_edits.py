"""restate the savings-goal ledger: edits now restate a goal's history

Revision ID: 5741e10f9f9a
Revises: 174ab4bac7b9
Create Date: 2026-10-09 10:00:00.000000

Changing a goal's start month, target, cap, opening balance or rules used to
restate history only for goals with income of their own; every other edit kept
past allocations as they were. Those stale rows are cleared here, as in
``174ab4bac7b9``, and recomputed on the next read. It is derived data only;
closed goals keep their frozen rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5741e10f9f9a"
down_revision: str | Sequence[str] | None = "174ab4bac7b9"
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
