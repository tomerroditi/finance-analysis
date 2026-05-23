"""strip "Auto: " prefix from tagging rule names

Revision ID: b2c4d6e8f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the legacy ``Auto: `` prefix from existing tagging rule names."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'tagging_rules' not in inspector.get_table_names():
        return
    conn.execute(
        sa.text(
            "UPDATE tagging_rules "
            "SET name = SUBSTR(name, 7) "
            "WHERE name LIKE 'Auto: %'"
        )
    )


def downgrade() -> None:
    """Re-apply the ``Auto: `` prefix to rule names that lack it."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'tagging_rules' not in inspector.get_table_names():
        return
    conn.execute(
        sa.text(
            "UPDATE tagging_rules "
            "SET name = 'Auto: ' || name "
            "WHERE name NOT LIKE 'Auto: %'"
        )
    )
