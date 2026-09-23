"""add clearing_house_reports table

Revision ID: b3d5f7a9c1e4
Revises: d9f1b3a5c7e2
Create Date: 2026-09-23 23:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d5f7a9c1e4"
down_revision: str | Sequence[str] | None = "d9f1b3a5c7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table of monthly clearing-house household summaries.

    Idempotent: a fresh DB already has the table from
    ``Base.metadata.create_all``, so the create is skipped there.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "clearing_house_reports" in inspector.get_table_names():
        return

    op.create_table(
        "clearing_house_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=False),
        sa.Column("calc_date", sa.String(), nullable=False),
        sa.Column("total_savings", sa.Float(), nullable=True),
        sa.Column("forecast_total_balance", sa.Float(), nullable=True),
        sa.Column("forecast_monthly_pension", sa.Float(), nullable=True),
        sa.Column("forecast_lump_sum", sa.Float(), nullable=True),
        sa.Column("disability_monthly", sa.Float(), nullable=True),
        sa.Column("survivor_spouse_monthly", sa.Float(), nullable=True),
        sa.Column("survivor_child_monthly", sa.Float(), nullable=True),
        sa.Column("death_lump_sum", sa.Float(), nullable=True),
        sa.Column("report_number", sa.Integer(), nullable=True),
        sa.Column("report_count", sa.Integer(), nullable=True),
        sa.Column("subscription_expires", sa.String(), nullable=True),
        sa.Column("subscription_months_left", sa.Integer(), nullable=True),
        sa.Column("license_holder", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider", "account_name", "calc_date", name="uq_clearing_house_report"
        ),
    )


def downgrade() -> None:
    """Drop the clearing_house_reports table."""
    op.drop_table("clearing_house_reports")
