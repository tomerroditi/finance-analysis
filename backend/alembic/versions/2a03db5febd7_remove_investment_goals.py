"""remove investment goals: savings goals are cash only

Revision ID: 2a03db5febd7
Revises: ee9bb63e5eaf
Create Date: 2026-10-09 18:00:00.000000

Investment goals tried to say, after the fact, which goal each investment
transfer belonged to, and every answer opened a new edge case. Savings goals
are cash earmarks again.

Existing investment goals are deleted with their links and allocations. Their
money was invested, not set aside, so none can become a cash goal: one fed by
a gift would claim cash that sits in an investment. How much a year saved, the
question they were standing in for, is measured on its own.

Then the ``kind`` and ``funding_*`` columns are dropped, and the open goals'
ledger is cleared to be recomputed on the next read, as in ``ee9bb63e5eaf``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a03db5febd7"
down_revision: str | Sequence[str] | None = "ee9bb63e5eaf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("kind", "funding_category", "funding_tags")


def upgrade() -> None:
    """Delete investment goals and drop the columns that described them."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "savings_goals" not in tables:
        return
    existing = {c["name"] for c in inspector.get_columns("savings_goals")}

    if "kind" in existing:
        doomed = "SELECT id FROM savings_goals WHERE kind = 'investment'"
        for child in ("savings_goal_allocations", "savings_goal_links"):
            if child in tables:
                conn.execute(
                    sa.text(f"DELETE FROM {child} WHERE goal_id IN ({doomed})")
                )
        conn.execute(sa.text("DELETE FROM savings_goals WHERE kind = 'investment'"))

    if "savings_goal_allocations" in tables:
        conn.execute(
            sa.text(
                "DELETE FROM savings_goal_allocations WHERE goal_id IN "
                "(SELECT id FROM savings_goals WHERE status != 'closed')"
            )
        )

    present = [name for name in _COLUMNS if name in existing]
    if present:
        with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
            for name in present:
                batch_op.drop_column(name)


def downgrade() -> None:
    """Restore the columns; the deleted investment goals are not recoverable."""
    with op.batch_alter_table("savings_goals") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(), nullable=True, server_default="cash")
        )
        batch_op.add_column(sa.Column("funding_category", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("funding_tags", sa.String(), nullable=True))
