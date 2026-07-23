"""add rate_spread to investments

Revision ID: d0e2f4a6b8c1
Revises: c9d1e3f5a7b9
Create Date: 2026-07-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d0e2f4a6b8c1"
down_revision: Union[str, Sequence[str], None] = "c9d1e3f5a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the rate_spread column for prime-linked investments.

    Idempotent: fresh DBs already have the column from
    ``Base.metadata.create_all``. Nullable with no backfill — only
    prime-linked investments (a new type) use it.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "investments" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("investments")]
    if "rate_spread" not in columns:
        with op.batch_alter_table("investments") as batch_op:
            batch_op.add_column(sa.Column("rate_spread", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove the rate_spread column."""
    with op.batch_alter_table("investments", recreate="always") as batch_op:
        batch_op.drop_column("rate_spread")
