"""add error_type to scraping_history

Splits a failed scrape's *category* from its *detail*. Before this, the single
``error_message`` column had to serve both audiences at once — it was rendered
verbatim in the UI, so anything diagnostic enough to debug with was too raw to
show a user, and anything friendly enough to show lost the provider's actual
message. ``error_type`` now carries the machine-readable category driving the
user-facing copy, leaving ``error_message`` free to hold the real provider text.

Revision ID: f2a4c6e8b0d3
Revises: e1f3a5b7c9d2
Create Date: 2026-07-25 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a4c6e8b0d3"
down_revision: Union[str, Sequence[str], None] = "e1f3a5b7c9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "scraping_history"
_COLUMN = "error_type"


def upgrade() -> None:
    """Add the nullable ``error_type`` column when it isn't already present.

    Migrations run after ``Base.metadata.create_all``, so a fresh database
    already has the column — the guard keeps this a no-op there rather than
    failing on a duplicate-column error.

    Existing rows keep ``error_type`` NULL. They are backfilled to nothing on
    purpose: their ``error_message`` was written under the old single-column
    scheme and guessing a category from that free text would invent history. The
    frontend treats a missing ``error_type`` as "show the stored message", which
    is exactly the old behaviour for old rows.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns(_TABLE)]
    if _COLUMN not in columns:
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(sa.Column(_COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the ``error_type`` column."""
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_column(_COLUMN)
