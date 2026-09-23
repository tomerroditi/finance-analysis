"""Add cash_balances table

Revision ID: 7beb5c98691f
Revises:
Create Date: 2026-02-21 15:37:26.516282

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7beb5c98691f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create cash_balances table if it doesn't exist
    # Note: Table may already exist from previous manual schema initialization
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "cash_balances" not in inspector.get_table_names():
        op.create_table(
            "cash_balances",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("account_name", sa.String(), nullable=False, unique=True),
            sa.Column("balance", sa.Float(), nullable=False),
            sa.Column(
                "prior_wealth_amount", sa.Float(), nullable=False, server_default="0.0"
            ),
            sa.Column("last_manual_update", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cash_balances")
