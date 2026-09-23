"""add insurance_loan_key to liabilities

Revision ID: c6e8a0b2d4f7
Revises: b3d5f7a9c1e4
Create Date: 2026-09-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6e8a0b2d4f7"
down_revision: str | Sequence[str] | None = "b3d5f7a9c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column linking a liability to a loan against a pension policy."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "liabilities" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("liabilities")]
    if "insurance_loan_key" not in columns:
        with op.batch_alter_table("liabilities") as batch_op:
            batch_op.add_column(
                sa.Column("insurance_loan_key", sa.String(), nullable=True)
            )
            batch_op.create_unique_constraint(
                "uq_liability_insurance_loan_key", ["insurance_loan_key"]
            )


def downgrade() -> None:
    """Remove the insurance_loan_key column from liabilities."""
    with op.batch_alter_table("liabilities", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_liability_insurance_loan_key", type_="unique")
        batch_op.drop_column("insurance_loan_key")
