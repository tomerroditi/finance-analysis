"""add details to insurance_accounts

Revision ID: d9f1b3a5c7e2
Revises: e7a9c1b3d5f8
Create Date: 2026-09-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f1b3a5c7e2"
down_revision: str | Sequence[str] | None = "e7a9c1b3d5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the details JSON column to insurance_accounts."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "insurance_accounts" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("insurance_accounts")]
    if "details" not in columns:
        with op.batch_alter_table("insurance_accounts") as batch_op:
            batch_op.add_column(sa.Column("details", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the details column from insurance_accounts."""
    with op.batch_alter_table("insurance_accounts") as batch_op:
        batch_op.drop_column("details")
