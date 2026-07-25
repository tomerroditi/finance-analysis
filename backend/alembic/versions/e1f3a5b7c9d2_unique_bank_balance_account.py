"""dedupe natural-key tables and enforce their uniqueness

Revision ID: e1f3a5b7c9d2
Revises: d0e2f4a6b8c1
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f3a5b7c9d2"
down_revision: Union[str, Sequence[str], None] = "d0e2f4a6b8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint name, natural-key columns)
_TARGETS: list[tuple[str, str, list[str]]] = [
    ("bank_balances", "uq_bank_balance_account", ["provider", "account_name"]),
    (
        "budget_month_overrides",
        "uq_budget_month_override_source",
        ["source_type", "source_id", "source_table"],
    ),
    (
        "pending_refunds",
        "uq_pending_refund_source",
        ["source_type", "source_id", "source_table"],
    ),
    (
        "refund_source_notes",
        "uq_refund_source_note",
        ["refund_source", "refund_transaction_id"],
    ),
]


def upgrade() -> None:
    """Collapse duplicate natural-key rows, then constrain each table.

    All four tables were written by read-then-write upserts, so two
    concurrent requests could both see "missing" and both insert. Afterwards
    every read of that key raised ``MultipleResultsFound`` — a permanent 500
    with no API path to repair it.

    Idempotent: fresh databases already carry these constraints from
    ``Base.metadata.create_all``, so each table is skipped. The dedupe keeps
    the lowest-id row, matching the readers' tie-break.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = set(inspector.get_table_names())

    for table, constraint, columns in _TARGETS:
        if table not in table_names:
            continue
        existing = {
            uc["name"] for uc in inspector.get_unique_constraints(table)
        }
        if constraint in existing:
            continue

        grouped = ", ".join(columns)
        conn.execute(
            sa.text(
                f"""
                DELETE FROM {table}
                WHERE id NOT IN (
                    SELECT MIN(id) FROM {table} GROUP BY {grouped}
                )
                """
            )
        )

        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.create_unique_constraint(constraint, columns)


def downgrade() -> None:
    """Drop the uniqueness constraints."""
    for table, constraint, _ in _TARGETS:
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.drop_constraint(constraint, type_="unique")
