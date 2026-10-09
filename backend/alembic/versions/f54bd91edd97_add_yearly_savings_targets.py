"""add yearly savings targets

Revision ID: f54bd91edd97
Revises: 2a03db5febd7
Create Date: 2026-10-09 20:00:00.000000

One row per calendar year: how much the user aims to save that year.
``create_all`` already builds the table on a fresh database, so this only
creates it where it is missing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f54bd91edd97"
down_revision: str | Sequence[str] | None = "2a03db5febd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``yearly_savings_targets`` if it does not exist yet."""
    if "yearly_savings_targets" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "yearly_savings_targets",
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    """Drop the yearly targets."""
    op.drop_table("yearly_savings_targets")
