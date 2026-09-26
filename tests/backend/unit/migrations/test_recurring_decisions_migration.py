"""Tests for the recurring_decisions table migration."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    """Import the recurring_decisions migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/f4a6c8e0b2d5_add_recurring_decisions.py"
    )
    spec = importlib.util.spec_from_file_location("recurring_decisions_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRecurringDecisionsMigration:
    """The migration creates the verdict table and is safe to re-run."""

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

            inspector = sa.inspect(conn)
            assert "recurring_decisions" in inspector.get_table_names()
            columns = {
                c["name"] for c in inspector.get_columns("recurring_decisions")
            }
            assert {"normalized", "decision", "label"} <= columns

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

        from backend.models.recurring_decision import RecurringDecision

        assert db_session.query(RecurringDecision).count() == 0
