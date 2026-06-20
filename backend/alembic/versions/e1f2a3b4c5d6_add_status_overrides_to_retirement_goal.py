"""Add status override columns to retirement_goal table.

Revision ID: e1f2a3b4c5d6
Revises: f1e2d3c4b5a6
Create Date: 2025-06-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add net_worth_override, monthly_expenses_override, total_investments_override columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    # Fresh DBs have the table created by Base.metadata.create_all() with
    # all columns already present; partial test DBs may not have the table.
    if "retirement_goal" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("retirement_goal")}
    new_cols = [
        ("net_worth_override", sa.Column("net_worth_override", sa.Float(), nullable=True)),
        ("monthly_expenses_override", sa.Column("monthly_expenses_override", sa.Float(), nullable=True)),
        ("total_investments_override", sa.Column("total_investments_override", sa.Float(), nullable=True)),
    ]
    missing = [(name, col) for name, col in new_cols if name not in columns]
    if missing:
        with op.batch_alter_table("retirement_goal") as batch_op:
            for _, col in missing:
                batch_op.add_column(col)


def downgrade() -> None:
    """Remove status override columns."""
    with op.batch_alter_table("retirement_goal") as batch_op:
        for col in ("net_worth_override", "monthly_expenses_override", "total_investments_override"):
            batch_op.drop_column(col)
