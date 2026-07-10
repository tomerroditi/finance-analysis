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

        # Seed a monthly and a project row with period_type unset.
        db_session.add(BudgetRule(name="Food", amount=100.0, category="Food",
                                  tags="Groceries", year=2026, month=5, period_type=None))
        db_session.add(BudgetRule(name="Total Budget", amount=5000.0, category="Reno",
                                  tags="all_tags", year=None, month=None, period_type=None))
        db_session.commit()

        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()  # second run must be a no-op, not an error

        rows = {r.name: r.period_type for r in db_session.query(BudgetRule).all()}
        assert rows["Food"] == "monthly"
        assert rows["Total Budget"] == "project"
