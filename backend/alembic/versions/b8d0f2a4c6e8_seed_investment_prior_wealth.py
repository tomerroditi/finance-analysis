"""seed investment prior wealth and drop legacy offset transactions

Revision ID: b8d0f2a4c6e8
Revises: a7c9e1b3d5f7
Create Date: 2026-07-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8d0f2a4c6e8"
down_revision: Union[str, Sequence[str], None] = "a7c9e1b3d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Literal values of PRIOR_WEALTH_TAG / IncomeCategories.OTHER_INCOME at the
# time of this migration — migrations must not import application constants
# (they'd silently rewrite history if the constant ever changes).
_PRIOR_WEALTH_TAG = "Prior Wealth"
_OTHER_INCOME = "Other Income"


def upgrade() -> None:
    """One-time replacement for the legacy lifespan data migration.

    Previously ``backend/main.py`` ran this on every boot: it added
    ``investments.prior_wealth_amount``, re-seeded it from
    ``manual_investment_transactions`` (overwriting any value that had
    drifted since), and deleted the legacy prior-wealth offset rows.
    Moving it here runs it exactly once per database; ongoing recalculation
    stays with InvestmentsService, which reacts to transaction changes.

    Idempotent: fresh DBs already have the column from
    ``Base.metadata.create_all`` and contain no legacy rows, so every step
    is a no-op there.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "investments" not in tables:
        return

    columns = [c["name"] for c in inspector.get_columns("investments")]
    column_added = "prior_wealth_amount" not in columns
    if column_added:
        with op.batch_alter_table("investments") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "prior_wealth_amount",
                    sa.Float(),
                    nullable=False,
                    server_default="0.0",
                )
            )

    if "manual_investment_transactions" not in tables:
        return

    # Drop the legacy consolidated prior-wealth offset transactions first so
    # they can't leak into the seeded sums.
    conn.execute(
        sa.text(
            "DELETE FROM manual_investment_transactions "
            "WHERE tag = :tag AND category = :category AND account_name = :tag"
        ),
        {"tag": _PRIOR_WEALTH_TAG, "category": _OTHER_INCOME},
    )

    # Seed prior_wealth_amount from each investment's transactions — exactly
    # what the legacy lifespan block recomputed on every boot, applied one
    # final time here. From now on the value is service-maintained
    # (recalculated when investment transactions change).
    conn.execute(
        sa.text(
            "UPDATE investments SET prior_wealth_amount = COALESCE("
            "  (SELECT -SUM(t.amount) FROM manual_investment_transactions t"
            "   WHERE t.category = investments.category"
            "     AND t.tag = investments.tag), 0.0)"
        )
    )


def downgrade() -> None:
    """Irreversible data migration — the deleted legacy rows cannot be restored."""
