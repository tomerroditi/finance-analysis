"""add monthly_income to retirement_goal

Revision ID: f1e2d3c4b5a6
Revises: ecec034aa367
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, Sequence[str], None] = 'ecec034aa367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add monthly_income column to retirement_goal table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('retirement_goal')]
    if 'monthly_income' not in columns:
        with op.batch_alter_table('retirement_goal') as batch_op:
            batch_op.add_column(sa.Column('monthly_income', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove monthly_income column from retirement_goal table."""
    with op.batch_alter_table('retirement_goal') as batch_op:
        batch_op.drop_column('monthly_income')
