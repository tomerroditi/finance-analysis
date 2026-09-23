"""add recurring_decisions table

Revision ID: f4a6c8e0b2d5
Revises: e3b5d7f9a1c2
Create Date: 2026-09-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a6c8e0b2d5"
down_revision: str | Sequence[str] | None = "e3b5d7f9a1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table holding user verdicts on detected recurring charges.

    Idempotent: a fresh DB already has the table from
    ``Base.metadata.create_all``, so the create is skipped there. No backfill —
    an absent row means *pending*, and every candidate detected before this
    feature existed should indeed go back through review rather than be
    silently adopted as confirmed.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "recurring_decisions" in inspector.get_table_names():
        return

    op.create_table(
        "recurring_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("normalized", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decided_amount", sa.Float(), nullable=True),
        sa.Column("decided_cadence", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized", name="uq_recurring_decision_normalized"),
    )
    op.create_index(
        "ix_recurring_decisions_normalized", "recurring_decisions", ["normalized"]
    )


def downgrade() -> None:
    """Drop the recurring_decisions table."""
    op.drop_index("ix_recurring_decisions_normalized", table_name="recurring_decisions")
    op.drop_table("recurring_decisions")
