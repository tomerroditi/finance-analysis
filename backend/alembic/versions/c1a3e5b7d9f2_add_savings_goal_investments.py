"""Add the savings_goal_investments table.

A savings goal can now be backed by an investment holding the user intends to
liquidate — bonds earmarked for a car, a savings plan maturing into a down
payment — rather than only by cash. The earmark is valued live from the
holding's balance, so the table stores just the link plus an optional partial
amount; ``NULL`` means "whatever is left of this holding".

Fresh databases already have the table from ``Base.metadata.create_all``, which
runs before migrations, so this is a no-op there.

Revision ID: c1a3e5b7d9f2
Revises: b7d4f1a9c3e2
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a3e5b7d9f2"
down_revision: Union[str, Sequence[str], None] = "b7d4f1a9c3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKINGS = "savings_goal_investments"


def upgrade() -> None:
    """Create the earmark table when it is not already present."""
    if BACKINGS in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        BACKINGS,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("goal_id", sa.Integer(), nullable=False, index=True),
        sa.Column("investment_id", sa.Integer(), nullable=False, index=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "goal_id", "investment_id", name="uq_savings_goal_investment"
        ),
    )


def downgrade() -> None:
    """Drop the earmark table."""
    if BACKINGS in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(BACKINGS)
