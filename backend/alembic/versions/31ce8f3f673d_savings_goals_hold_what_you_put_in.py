"""savings goals hold what you put in: entries replace the allocation ledger

Revision ID: 31ce8f3f673d
Revises: f54bd91edd97
Create Date: 2026-10-10 12:00:00.000000

Goals stop being filled automatically. A goal now holds the money the user put
into it (``savings_goal_entries``), plus its own income, less its spending;
free cash is the bank and cash money no goal holds.

Every goal keeps exactly what it holds today. Each month the old ledger gave a
goal (a negative month is a clawback) becomes an entry dated the first of that
month, and an opening balance becomes an entry at the goal's start, so a
goal's history reads the same as before. Then:

- ``savings_goal_allocations`` is dropped;
- ``monthly_cap`` becomes ``monthly_amount`` — what the card suggests putting
  in each month — and ``opening_balance`` is dropped;
- per-transaction contribution links on money going *out* are removed: only
  income can be saved into a goal now, and setting money aside is an entry.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31ce8f3f673d"
down_revision: str | Sequence[str] | None = "f54bd91edd97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRANSACTION_TABLES = (
    "bank_transactions",
    "cash_transactions",
    "credit_card_transactions",
    "manual_investment_transactions",
)


def upgrade() -> None:
    """Carry every goal's money into entries and retire the allocation ledger."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    # Startup's ``create_all`` usually made this table already (without the
    # timestamp defaults), so the inserts below set every column themselves.
    if "savings_goal_entries" not in tables:
        op.create_table(
            "savings_goal_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("goal_id", sa.Integer(), nullable=False, index=True),
            sa.Column("date", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if "savings_goals" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("savings_goals")}

    if "opening_balance" in columns:
        conn.execute(
            sa.text(
                "INSERT INTO savings_goal_entries "
                "(goal_id, date, amount, source, note, created_at, updated_at) "
                "SELECT id, COALESCE(start_month, strftime('%Y-%m', created_at)) "
                "|| '-01', opening_balance, 'migrated', 'Opening balance', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM savings_goals WHERE opening_balance > 0"
            )
        )
    if "savings_goal_allocations" in tables:
        conn.execute(
            sa.text(
                "INSERT INTO savings_goal_entries "
                "(goal_id, date, amount, source, created_at, updated_at) "
                "SELECT goal_id, printf('%04d-%02d-01', year, month), amount, "
                "'migrated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM savings_goal_allocations "
                "WHERE ABS(amount) >= 0.005 "
                "AND goal_id IN (SELECT id FROM savings_goals) "
                "ORDER BY year, month, goal_id"
            )
        )
        op.drop_table("savings_goal_allocations")

    if "savings_goal_links" in tables:
        for table in _TRANSACTION_TABLES:
            if table not in tables:
                continue
            conn.execute(
                sa.text(
                    "DELETE FROM savings_goal_links WHERE link_type = 'contribution' "
                    "AND source_type = 'transaction' AND source_table = :table "
                    f"AND source_id IN (SELECT unique_id FROM {table} WHERE amount < 0)"
                ),
                {"table": table},
            )
        if "split_transactions" in tables:
            conn.execute(
                sa.text(
                    "DELETE FROM savings_goal_links WHERE link_type = 'contribution' "
                    "AND source_type = 'split' AND source_id IN "
                    "(SELECT id FROM split_transactions WHERE amount < 0)"
                )
            )

    if "monthly_amount" not in columns:
        with op.batch_alter_table("savings_goals") as batch_op:
            batch_op.add_column(sa.Column("monthly_amount", sa.Float(), nullable=True))
        if "monthly_cap" in columns:
            conn.execute(
                sa.text("UPDATE savings_goals SET monthly_amount = monthly_cap")
            )
    retired = [name for name in ("monthly_cap", "opening_balance") if name in columns]
    if retired:
        with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
            for name in retired:
                batch_op.drop_column(name)


def downgrade() -> None:
    """Restore the old columns and an empty ledger; entries are not converted back."""
    with op.batch_alter_table("savings_goals") as batch_op:
        batch_op.add_column(
            sa.Column("opening_balance", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("monthly_cap", sa.Float(), nullable=True))
    op.execute("UPDATE savings_goals SET monthly_cap = monthly_amount")
    with op.batch_alter_table("savings_goals", recreate="always") as batch_op:
        batch_op.drop_column("monthly_amount")
    op.create_table(
        "savings_goal_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("goal_id", sa.Integer(), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "goal_id", "year", "month", name="uq_savings_goal_allocation_month"
        ),
    )
    op.drop_table("savings_goal_entries")
