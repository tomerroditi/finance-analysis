"""add balance source and drift to bank_balances

Revision ID: 7c1e9a3b5d20
Revises: 31ce8f3f673d
Create Date: 2026-10-10 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1e9a3b5d20"
down_revision: str | Sequence[str] | None = "31ce8f3f673d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("balance_source", sa.String()),
    ("last_drift", sa.Float()),
)


def upgrade() -> None:
    """Record where each balance came from and how far the bank's differed."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "bank_balances" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("bank_balances")}
    missing = [(name, kind) for name, kind in _COLUMNS if name not in existing]
    if not missing:
        return
    with op.batch_alter_table("bank_balances") as batch_op:
        for name, kind in missing:
            batch_op.add_column(sa.Column(name, kind, nullable=True))
    if "balance_source" in {name for name, _ in missing}:
        conn.exec_driver_sql(
            "UPDATE bank_balances SET balance_source = 'manual' "
            "WHERE last_manual_update IS NOT NULL"
        )


def downgrade() -> None:
    """Drop the balance source and drift columns."""
    with op.batch_alter_table("bank_balances", recreate="always") as batch_op:
        batch_op.drop_column("last_drift")
        batch_op.drop_column("balance_source")
