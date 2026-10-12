"""add billing_date to credit_card_transactions

Revision ID: 9d3f5b7a1c42
Revises: b7d9f1a3c5e2
Create Date: 2026-10-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d3f5b7a1c42"
down_revision: str | Sequence[str] | None = "b7d9f1a3c5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "credit_card_transactions"


def upgrade() -> None:
    """Record the day the card company charged each purchase to the bank."""
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if "billing_date" in {c["name"] for c in inspector.get_columns(_TABLE)}:
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(sa.Column("billing_date", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the billing date column."""
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_column("billing_date")
