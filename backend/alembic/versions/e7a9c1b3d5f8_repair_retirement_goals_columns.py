"""repair retirement_goals columns missed by a mistyped table name

Two earlier revisions guarded on ``retirement_goal`` (singular) while the
table is ``retirement_goals``. ``inspector.get_table_names()`` never contained
the singular name, so both took their "table absent, nothing to do" branch,
returned, and were stamped as applied — leaving four columns the ORM maps
absent on every database that predates them.

The symptom is not subtle: ``GET /api/retirement/goal`` and
``/api/retirement/projections`` 500 with ``no such column:
retirement_goals.monthly_income``, so the dashboard's retirement card is dead
and React Query retries both. Fresh installs were unaffected — there
``Base.metadata.create_all`` builds the table from the current model — which
is why this survived.

The two revisions are fixed in place as well, but a stamped revision never
runs again, so repairing existing databases needs this new one.

Revision ID: e7a9c1b3d5f8
Revises: c5b7e9d1f3a8
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a9c1b3d5f8"
down_revision: Union[str, Sequence[str], None] = "c5b7e9d1f3a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "retirement_goals"

#: Every column the two mistyped revisions were supposed to add.
COLUMNS = (
    ("monthly_income", sa.Float()),
    ("net_worth_override", sa.Float()),
    ("monthly_expenses_override", sa.Float()),
    ("total_investments_override", sa.Float()),
)


def upgrade() -> None:
    """Add whichever of the four columns are missing."""
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    missing = [(name, type_) for name, type_ in COLUMNS if name not in existing]
    if not missing:
        return

    with op.batch_alter_table(TABLE) as batch_op:
        for name, type_ in missing:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """Drop the four columns, ignoring any the database does not have."""
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    present = [name for name, _ in COLUMNS if name in existing]
    if not present:
        return

    with op.batch_alter_table(TABLE) as batch_op:
        for name in present:
            batch_op.drop_column(name)
