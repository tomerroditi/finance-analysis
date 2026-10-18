"""Tests for the applied_data_fixes table migration."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration():
    """Import the applied_data_fixes migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/a9c1e3f5b7d9_add_applied_data_fixes.py"
    )
    spec = importlib.util.spec_from_file_location("applied_data_fixes_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAppliedDataFixesMigration:
    """The migration creates the fix ledger and is safe to re-run."""

    def test_creates_table_on_legacy_schema(self, tmp_path):
        """A DB predating the ledger gains the table with a unique name."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        mig = _load_migration()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mig.upgrade()
            conn.commit()

            inspector = sa.inspect(conn)
            assert "applied_data_fixes" in inspector.get_table_names()
            columns = {c["name"] for c in inspector.get_columns("applied_data_fixes")}
            assert {"id", "name", "created_at", "updated_at"} <= columns
            uniques = inspector.get_unique_constraints("applied_data_fixes")
            assert [u["column_names"] for u in uniques] == [["name"]]
        engine.dispose()

    def test_rerun_is_a_no_op(self, db_session):
        """A fresh DB already has the table from create_all — running is harmless."""
        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()

        from backend.models.applied_data_fix import AppliedDataFix

        assert db_session.query(AppliedDataFix).count() == 0
