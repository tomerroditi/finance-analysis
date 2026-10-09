"""Tests for the fire_scenarios table migration."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    """Import the fire_scenarios migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/b7d9f1a3c5e2_add_fire_scenarios.py"
    )
    spec = importlib.util.spec_from_file_location("fire_scenarios_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFireScenariosMigration:
    """The migration creates the saved-plan table and is safe to re-run."""

    def test_creates_table_on_legacy_schema(self, tmp_path):
        """A DB predating the feature gains the table with the expected columns."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        mig = _load_migration()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mig.upgrade()
            conn.commit()

            columns = {c["name"] for c in sa.inspect(conn).get_columns("fire_scenarios")}
            assert {"fields", "linked", "created_at", "updated_at"} <= columns

        engine.dispose()

    def test_rerun_is_a_no_op(self, db_session):
        """A fresh DB already has the table from create_all — running is harmless."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()

        from backend.models.fire_scenario import FireScenario

        assert db_session.query(FireScenario).count() == 0
