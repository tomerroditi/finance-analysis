"""drop savings_goal_investments

Revision ID: b9a0f25d4d28
Revises: 395a5712d6e3
Create Date: 2026-09-26 22:00:00.000000

Investment backing is gone: an investment is a category and tag, so a goal
that tracks money moved into one is an investment goal (``savings_goals.kind``)
rather than an earmark valued off a holding.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9a0f25d4d28"
down_revision: str | Sequence[str] | None = "395a5712d6e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the investment-earmark table if it exists."""
    conn = op.get_bind()
    if "savings_goal_investments" in sa.inspect(conn).get_table_names():
        op.drop_table("savings_goal_investments")


def downgrade() -> None:
    """Recreate the (empty) investment-earmark table."""
    op.create_table(
        "savings_goal_investments",
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
