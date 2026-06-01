"""add performance indexes to transaction, scraping and snapshot tables

Revision ID: c3d5e7f9a1b3
Revises: b2c4d6e8f0a1
Create Date: 2026-06-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b3'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Transaction tables sharing the same index layout (date, source,
# provider+account_name, category+tag).
_TRANSACTION_TABLES = (
    "bank_transactions",
    "credit_card_transactions",
    "cash_transactions",
    "manual_investment_transactions",
    "insurance_transactions",
)

# (index_name, table_name, [columns]) for every index this migration owns,
# ordered so creation is safe; downgrade drops them in reverse.
def _index_specs() -> list[tuple[str, str, list[str]]]:
    specs: list[tuple[str, str, list[str]]] = []
    for table in _TRANSACTION_TABLES:
        specs.append((f"ix_{table}_date", table, ["date"]))
        specs.append((f"ix_{table}_source", table, ["source"]))
        specs.append(
            (f"ix_{table}_provider_account_name", table, ["provider", "account_name"])
        )
        specs.append((f"ix_{table}_category_tag", table, ["category", "tag"]))
    specs.append(("ix_split_transactions_source", "split_transactions", ["source"]))
    specs.append(
        (
            "ix_split_transactions_transaction_id",
            "split_transactions",
            ["transaction_id"],
        )
    )
    specs.append(
        (
            "ix_scraping_history_service_provider_account_status",
            "scraping_history",
            ["service_name", "provider_name", "account_name", "status"],
        )
    )
    specs.append(("ix_scraping_history_date", "scraping_history", ["date"]))
    specs.append(
        (
            "ix_investment_balance_snapshots_date",
            "investment_balance_snapshots",
            ["date"],
        )
    )
    return specs


def upgrade() -> None:
    """Create indexes on heavily filtered/grouped analytics columns.

    Idempotent: ``Base.metadata.create_all`` runs before Alembic on startup and
    may already have created these indexes on a fresh database, so each index
    is created only when both its table exists and the index is absent.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    existing_by_table: dict[str, set[str]] = {}

    for name, table, columns in _index_specs():
        if table not in existing_tables:
            continue
        if table not in existing_by_table:
            existing_by_table[table] = {
                idx["name"] for idx in inspector.get_indexes(table)
            }
        if name in existing_by_table[table]:
            continue
        op.create_index(name, table, columns)
        existing_by_table[table].add(name)


def downgrade() -> None:
    """Drop the performance indexes created in :func:`upgrade`."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    existing_by_table: dict[str, set[str]] = {}

    for name, table, _columns in reversed(_index_specs()):
        if table not in existing_tables:
            continue
        if table not in existing_by_table:
            existing_by_table[table] = {
                idx["name"] for idx in inspector.get_indexes(table)
            }
        if name not in existing_by_table[table]:
            continue
        op.drop_index(name, table_name=table)
        existing_by_table[table].discard(name)
