"""add insight_dismissals table

Revision ID: c5b7e9d1f3a8
Revises: f4a6c8e0b2d5
Create Date: 2026-09-14 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5b7e9d1f3a8"
down_revision: str | Sequence[str] | None = "f4a6c8e0b2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table holding the insight cards the user has dismissed.

    Idempotent: a fresh DB already has the table from
    ``Base.metadata.create_all``, so the create is skipped there. No backfill —
    an absent row means the card has never been waved away, which is the right
    starting point for every existing user.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "insight_dismissals" in inspector.get_table_names():
        return

    op.create_table(
        "insight_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_insight_dismissal_key"),
    )
    op.create_index("ix_insight_dismissals_key", "insight_dismissals", ["key"])


def downgrade() -> None:
    """Drop the insight_dismissals table."""
    op.drop_index("ix_insight_dismissals_key", table_name="insight_dismissals")
    op.drop_table("insight_dismissals")
