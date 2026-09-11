"""Label legacy closing snapshots with the ``closed`` source.

Closing an investment writes a zero snapshot on its last transaction date.
Before the ``closed`` source existed that zero was stored as ``manual``,
indistinguishable from a valuation the user typed. The closing zero now
follows the investment when a transaction lands after the close, which only
works for a row the app can recognise as the close — so a closed investment's
newest snapshot, when it is a zero, is relabelled.

Downgrade leaves the labels alone: ``manual`` carried nothing ``closed`` does
not, and restoring it would only stop the zero from following later
transactions.

Revision ID: d4e6f8a0b2c4
Revises: c1a3e5b7d9f2
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a0b2c4"
down_revision: Union[str, Sequence[str], None] = "c1a3e5b7d9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Relabel each closed investment's final zero snapshot as ``closed``."""
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "investments" not in tables or "investment_balance_snapshots" not in tables:
        return

    bind.execute(
        sa.text(
            """
            UPDATE investment_balance_snapshots
            SET source = 'closed'
            WHERE balance = 0
              AND COALESCE(source, '') != 'closed'
              AND investment_id IN (SELECT id FROM investments WHERE is_closed = 1)
              AND date = (
                  SELECT MAX(latest.date)
                  FROM investment_balance_snapshots AS latest
                  WHERE latest.investment_id = investment_balance_snapshots.investment_id
              )
            """
        )
    )


def downgrade() -> None:
    """Keep the ``closed`` labels; see the module docstring."""
