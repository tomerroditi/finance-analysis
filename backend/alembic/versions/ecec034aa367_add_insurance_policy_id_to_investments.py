"""add insurance_policy_id to investments

Revision ID: ecec034aa367
Revises: 7beb5c98691f
Create Date: 2026-03-11 20:26:47.448217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ecec034aa367'
down_revision: Union[str, Sequence[str], None] = '7beb5c98691f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add insurance_policy_id column to investments table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('investments')]
    if 'insurance_policy_id' not in columns:
        op.add_column('investments', sa.Column('insurance_policy_id', sa.String(), nullable=True, unique=True))


def downgrade() -> None:
    """Remove insurance_policy_id column from investments table."""
    op.drop_column('investments', 'insurance_policy_id')
