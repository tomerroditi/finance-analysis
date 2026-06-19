"""drop legacy unique constraints on transaction tables

Revision ID: d4f6a8c0e2b5
Revises: c3d5e7f9a1b3
Create Date: 2026-06-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f6a8c0e2b5'
down_revision: Union[str, Sequence[str], None] = 'c3d5e7f9a1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Legacy named UNIQUE constraints that exist only in on-disk databases created
# before these constraints were removed from the ORM models. Each tuple is
# (table_name, constraint_name, [columns]). The columns are only used by
# downgrade() to recreate the constraint.
_LEGACY_UNIQUE_CONSTRAINTS = (
    (
        "bank_transactions",
        "bank_transactions_unique",
        ["provider", "date", "amount", "id"],
    ),
    (
        "credit_card_transactions",
        "credit_card_transactions_unique",
        ["provider", "date", "amount", "id"],
    ),
)


def _unique_constraint_names(conn, table: str) -> set[str]:
    """Return the set of named unique-constraint names on ``table``.

    Parameters
    ----------
    conn : sqlalchemy.engine.Connection
        Live connection bound to the migration context.
    table : str
        Table whose unique constraints should be inspected.

    Returns
    -------
    set of str
        Names of the table's unique constraints (unnamed ones are skipped).
    """
    inspector = sa.inspect(conn)
    return {
        uc["name"]
        for uc in inspector.get_unique_constraints(table)
        if uc.get("name")
    }


def upgrade() -> None:
    """Drop the legacy unique constraints that double-block genuine duplicates.

    A single scrape batch can legitimately contain two distinct transactions
    that share the tuple ``(provider, date, amount, id)`` — e.g. two identical
    ATM withdrawals on the same day where the bank returns the same (or empty)
    reference id. The legacy ``*_unique`` constraints reject the whole batch
    with an ``IntegrityError`` and the scrape fails. Dropping them lets the
    first scrape persist both rows; the existence-based dedup in
    ``TransactionsRepository.add_scraped_transactions`` still prevents
    re-scrape duplication.

    Notes
    -----
    Idempotent on two axes. ``Base.metadata.create_all`` runs before Alembic
    on startup; on a fresh database it creates the tables straight from the
    current ORM models, which declare no such constraint, so there is nothing
    to drop. We therefore only drop a constraint when its table exists *and*
    the named constraint is actually present. SQLite cannot drop a constraint
    in place, so we recreate the table via ``batch_alter_table(...,
    recreate='always')``.
    """
    conn = op.get_bind()
    existing_tables = set(sa.inspect(conn).get_table_names())

    for table, name, _columns in _LEGACY_UNIQUE_CONSTRAINTS:
        if table not in existing_tables:
            continue
        if name not in _unique_constraint_names(conn, table):
            continue
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.drop_constraint(name, type_="unique")


def downgrade() -> None:
    """Recreate the legacy unique constraints dropped in :func:`upgrade`.

    Notes
    -----
    Idempotent: only recreate a constraint when its table exists and the named
    constraint is currently absent, so re-running downgrade (or running it
    against a database that never had the constraint dropped) is a no-op.
    """
    conn = op.get_bind()
    existing_tables = set(sa.inspect(conn).get_table_names())

    for table, name, columns in _LEGACY_UNIQUE_CONSTRAINTS:
        if table not in existing_tables:
            continue
        if name in _unique_constraint_names(conn, table):
            continue
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.create_unique_constraint(name, columns)
