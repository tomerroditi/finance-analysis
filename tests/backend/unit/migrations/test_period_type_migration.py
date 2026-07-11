import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    """Import the period_type migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/a7c9e1b3d5f7_add_period_type_to_budget_rules.py"
    )
    spec = importlib.util.spec_from_file_location("period_type_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPeriodTypeMigration:
    """The period_type backfill migration is correct and idempotent."""

    def test_backfill_classifies_existing_rows(self, db_session):
        """Monthly/project rows get the right period_type; running twice is safe."""
        from backend.models.budget import BudgetRule
        from alembic import op
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        # Seed a monthly, a project, and a yearly row with period_type unset.
        db_session.add(BudgetRule(name="Food", amount=100.0, category="Food",
                                  tags="Groceries", year=2026, month=5, period_type=None))
        db_session.add(BudgetRule(name="Total Budget", amount=5000.0, category="Reno",
                                  tags="all_tags", year=None, month=None, period_type=None))
        db_session.add(BudgetRule(name="Annual Insurance", amount=1200.0, category="Insurance",
                                  tags="all_tags", year=2026, month=None, period_type=None))
        db_session.commit()

        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()  # second run must be a no-op, not an error

        rows = {r.name: r.period_type for r in db_session.query(BudgetRule).all()}
        assert rows["Food"] == "monthly"
        assert rows["Total Budget"] == "project"
        assert rows["Annual Insurance"] == "yearly"

    def test_upgrade_adds_column_on_legacy_schema(self, tmp_path):
        """The ADD COLUMN branch runs (and backfills correctly) against a
        pre-migration schema that has no period_type column at all."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        db_path = tmp_path / "legacy.db"
        engine = sa.create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE budget_rules ("
                    "id INTEGER PRIMARY KEY, name TEXT, amount REAL, category TEXT, "
                    "tags TEXT, year INTEGER, month INTEGER, "
                    "created_at TEXT, updated_at TEXT)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO budget_rules (name, amount, category, tags, year, month) "
                    "VALUES ('Food', 100.0, 'Food', 'Groceries', 2026, 5)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO budget_rules (name, amount, category, tags, year, month) "
                    "VALUES ('Total Budget', 5000.0, 'Reno', 'all_tags', NULL, NULL)"
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
            assert "period_type" in columns

            rows = {
                row[0]: row[1]
                for row in conn.execute(
                    sa.text("SELECT name, period_type FROM budget_rules")
                ).fetchall()
            }
            assert rows["Food"] == "monthly"
            assert rows["Total Budget"] == "project"

        engine.dispose()
