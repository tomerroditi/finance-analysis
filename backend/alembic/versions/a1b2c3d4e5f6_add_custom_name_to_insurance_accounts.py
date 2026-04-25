"""add custom_name to insurance_accounts

Revision ID: a1b2c3d4e5f6
Revises: ecec034aa367
Create Date: 2026-04-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'ecec034aa367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add custom_name column to insurance_accounts table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'insurance_accounts' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('insurance_accounts')]
    if 'custom_name' not in columns:
        with op.batch_alter_table('insurance_accounts') as batch_op:
            batch_op.add_column(sa.Column('custom_name', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove custom_name column from insurance_accounts table."""
    with op.batch_alter_table('insurance_accounts') as batch_op:
        batch_op.drop_column('custom_name')
