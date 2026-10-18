"""Drop the stored ``closed`` snapshots; valuation derives the closing zero.

A closed investment's zero used to be a stored snapshot that every write path
had to drag onto the investment's latest transaction. Valuation now derives it
on every read from the transactions themselves, so a stored copy is redundant
at best, and a stale one — left behind on reopen, or by a transaction landing
after this revision — would sit before the derived zero and undervalue the
fund in between. Only ``source = 'closed'`` rows go; a zero the user typed is
a valuation and stays.

Downgrade restores nothing: the previous code re-derives its zero the next
time it realigns.

Revision ID: b2d4f6a8c0e1
Revises: a9c1e3f5b7d9
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: str | Sequence[str] | None = "a9c1e3f5b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Delete every stored closing zero."""
    bind = op.get_bind()
    if "investment_balance_snapshots" not in sa.inspect(bind).get_table_names():
        return
    bind.execute(
        sa.text("DELETE FROM investment_balance_snapshots WHERE source = 'closed'")
    )


def downgrade() -> None:
    """Restore nothing; see the module docstring."""
