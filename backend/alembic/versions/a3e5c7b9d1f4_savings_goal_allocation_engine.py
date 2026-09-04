"""Give savings goals a priority waterfall, an allocation ledger, and transaction links.

Turns savings goals from a manually-typed ``current_amount`` into a derived
earmark: ``opening_balance`` seeds the goal, ``savings_goal_allocations`` holds
the per-month surplus distribution, and ``savings_goal_links`` attaches
individual transactions as contributions or utilizations.

Revision ID: a3e5c7b9d1f4
Revises: f2a4c6e8b0d3
Create Date: 2026-09-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3e5c7b9d1f4"
down_revision: Union[str, Sequence[str], None] = "f2a4c6e8b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GOALS = "savings_goals"
ALLOCATIONS = "savings_goal_allocations"
LINKS = "savings_goal_links"

NEW_GOAL_COLUMNS = [
    ("opening_balance", sa.Column("opening_balance", sa.Float(), nullable=False, server_default="0")),
    ("priority", sa.Column("priority", sa.Integer(), nullable=False, server_default="0")),
    ("monthly_cap", sa.Column("monthly_cap", sa.Float(), nullable=True)),
    ("start_month", sa.Column("start_month", sa.String(), nullable=True)),
    ("contribution_category", sa.Column("contribution_category", sa.String(), nullable=True)),
    ("contribution_tags", sa.Column("contribution_tags", sa.String(), nullable=True)),
    ("status", sa.Column("status", sa.String(), nullable=False, server_default="active")),
    ("closed_month", sa.Column("closed_month", sa.String(), nullable=True)),
]

# Goals predating `priority` all default to 0, which leaves the waterfall order
# arbitrary. Seed it from insertion order so the ranking is at least stable.
SEED_PRIORITY = (
    "UPDATE savings_goals SET priority = ("
    " SELECT COUNT(*) FROM savings_goals AS earlier WHERE earlier.id < savings_goals.id)"
)

# `current_amount` was the hand-typed progress figure the engine replaces.
# Carry any value across so a goal that did hold a number keeps it.
CARRY_CURRENT_AMOUNT = (
    "UPDATE savings_goals SET opening_balance = COALESCE(current_amount, 0)"
    " WHERE COALESCE(opening_balance, 0) = 0"
)


def _upgrade_goals_table(conn, inspector) -> None:
    """Add the new goal columns and retire ``current_amount``."""
    existing = {c["name"] for c in inspector.get_columns(GOALS)}
    missing = [(name, col) for name, col in NEW_GOAL_COLUMNS if name not in existing]
    if missing:
        with op.batch_alter_table(GOALS) as batch_op:
            for _, col in missing:
                batch_op.add_column(col)
    if any(name == "priority" for name, _ in missing):
        conn.execute(sa.text(SEED_PRIORITY))

    if "current_amount" in existing:
        conn.execute(sa.text(CARRY_CURRENT_AMOUNT))
        # recreate="always" is required for SQLite to actually drop a column.
        with op.batch_alter_table(GOALS, recreate="always") as batch_op:
            batch_op.drop_column("current_amount")


def upgrade() -> None:
    """Extend savings_goals and create the allocation + link tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    # Fresh DBs already have everything from Base.metadata.create_all(); this
    # migration only has to catch up databases created before the engine landed.
    if GOALS in tables:
        _upgrade_goals_table(conn, inspector)

    if ALLOCATIONS not in tables:
        op.create_table(
            ALLOCATIONS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("goal_id", sa.Integer(), nullable=False, index=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(), nullable=False, server_default="auto"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "goal_id", "year", "month", name="uq_savings_goal_allocation_month"
            ),
        )

    if LINKS not in tables:
        op.create_table(
            LINKS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("goal_id", sa.Integer(), nullable=False, index=True),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("source_table", sa.String(), nullable=False),
            sa.Column("link_type", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "source_type", "source_id", "source_table",
                name="uq_savings_goal_link_source",
            ),
        )


def downgrade() -> None:
    """Drop the allocation/link tables and the added goal columns."""
    op.drop_table(LINKS)
    op.drop_table(ALLOCATIONS)
    with op.batch_alter_table(GOALS, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("current_amount", sa.Float(), nullable=False, server_default="0")
        )
        for name, _ in NEW_GOAL_COLUMNS:
            batch_op.drop_column(name)
