import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    """Import the is_closed migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/e3b5d7f9a1c2_add_is_closed_to_budget_rules.py"
    )
    spec = importlib.util.spec_from_file_location("is_closed_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestIsClosedMigration:
    """The is_closed migration backfills existing rules as open, idempotently."""

    def test_existing_rules_read_as_open(self, db_session):
        """A rule predating the column ends up at 0, and a rerun is a no-op."""
        from backend.models.budget import BudgetRule
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        db_session.add(
            BudgetRule(
                name="Total Budget",
                amount=5000.0,
                category="Reno",
                tags="all_tags",
                year=None,
                month=None,
                period_type="project",
                is_closed=None,
            )
        )
        db_session.commit()

        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()  # second run must be a no-op, not an error

        rows = {r.name: r.is_closed for r in db_session.query(BudgetRule).all()}
        assert rows["Total Budget"] == 0

    def test_upgrade_adds_column_on_legacy_schema(self, tmp_path):
        """The ADD COLUMN branch runs against a schema with no is_closed column."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        db_path = tmp_path / "legacy.db"
        engine = sa.create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE budget_rules ("
                    "id INTEGER PRIMARY KEY, name TEXT, amount REAL, category TEXT, "
                    "tags TEXT, year INTEGER, month INTEGER, period_type TEXT, "
                    "created_at TEXT, updated_at TEXT)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO budget_rules "
                    "(name, amount, category, tags, year, month, period_type) "
                    "VALUES ('Total Budget', 5000.0, 'Reno', 'all_tags', "
                    "NULL, NULL, 'project')"
                )
            )

        mig = _load_migration()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mig.upgrade()
            conn.commit()

            inspector = sa.inspect(conn)
            columns = [c["name"] for c in inspector.get_columns("budget_rules")]
            assert "is_closed" in columns

            rows = {
                row[0]: row[1]
                for row in conn.execute(
                    sa.text("SELECT name, is_closed FROM budget_rules")
                ).fetchall()
            }
            assert rows["Total Budget"] == 0

        engine.dispose()
