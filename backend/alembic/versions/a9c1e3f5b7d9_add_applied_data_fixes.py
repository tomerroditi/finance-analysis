"""add applied_data_fixes table

Revision ID: a9c1e3f5b7d9
Revises: e3c5a7b9d1f2
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c1e3f5b7d9"
down_revision: str | Sequence[str] | None = "e3c5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table recording which one-time data fixes have run.

    Idempotent: a fresh DB already has the table from
    ``Base.metadata.create_all``. No backfill — an absent row means the fix
    has not run, which is true of every database before this revision.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "applied_data_fixes" in inspector.get_table_names():
        return

    op.create_table(
        "applied_data_fixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name", name="uq_applied_data_fixes_name"),
    )


def downgrade() -> None:
    """Drop the applied_data_fixes table."""
    op.drop_table("applied_data_fixes")
