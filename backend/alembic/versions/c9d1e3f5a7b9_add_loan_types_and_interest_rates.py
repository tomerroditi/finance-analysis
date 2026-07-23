"""add loan type fields to liabilities and interest_rates table

Revision ID: c9d1e3f5a7b9
Revises: b8d0f2a4c6e8
Create Date: 2026-07-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d1e3f5a7b9"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a4c6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_LIABILITY_COLUMNS = [
    ("loan_type", sa.String()),
    ("amortization_method", sa.String()),
    ("rate_spread", sa.Float()),
    ("rate_reset_months", sa.Integer()),
]


def upgrade() -> None:
    """Add loan-type columns and the interest_rates table.

    Idempotent: fresh DBs already have both from
    ``Base.metadata.create_all``. Existing liabilities are backfilled as
    fixed-rate Shpitzer loans — the only behavior that existed before
    this feature.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "liabilities" in tables:
        columns = [c["name"] for c in inspector.get_columns("liabilities")]
        missing = [(n, t) for n, t in _NEW_LIABILITY_COLUMNS if n not in columns]
        if missing:
            with op.batch_alter_table("liabilities") as batch_op:
                for name, col_type in missing:
                    batch_op.add_column(sa.Column(name, col_type, nullable=True))

        conn.execute(
            sa.text(
                "UPDATE liabilities SET loan_type = 'fixed_unlinked' "
                "WHERE loan_type IS NULL OR loan_type = ''"
            )
        )
        conn.execute(
            sa.text(
                "UPDATE liabilities SET amortization_method = 'shpitzer' "
                "WHERE amortization_method IS NULL OR amortization_method = ''"
            )
        )

    if "interest_rates" not in tables:
        op.create_table(
            "interest_rates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("series", sa.String(), nullable=False),
            sa.Column("date", sa.String(), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="seed"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("series", "date", name="uq_interest_rate_series_date"),
        )


def downgrade() -> None:
    """Remove the loan-type columns and the interest_rates table."""
    with op.batch_alter_table("liabilities", recreate="always") as batch_op:
        for name, _ in _NEW_LIABILITY_COLUMNS:
            batch_op.drop_column(name)
    op.drop_table("interest_rates")
