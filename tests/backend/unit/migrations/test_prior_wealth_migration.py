"""Tests for the seed-investment-prior-wealth migration (b8d0f2a4c6e8)."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration():
    """Import the prior-wealth migration module by file path."""
    path = (
        Path(__file__).resolve().parents[4]
        / "backend/alembic/versions/b8d0f2a4c6e8_seed_investment_prior_wealth.py"
    )
    spec = importlib.util.spec_from_file_location("prior_wealth_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPriorWealthMigration:
    """The prior-wealth seed migration is correct and idempotent."""

    def test_seeds_prior_wealth_and_drops_offset_rows(self, db_session):
        """Verify seeding from transactions, offset-row cleanup, and idempotency."""
        from backend.models.investment import Investment
        from backend.models.transaction import ManualInvestmentTransaction

        inv = Investment(
            name="Stocks", category="Investments", tag="Stocks", type="stocks",
            created_date="2024-01-01", is_closed=False, prior_wealth_amount=0.0,
        )
        db_session.add(inv)
        db_session.add(ManualInvestmentTransaction(
            id="1", date="2024-01-01", amount=-1000.0, description="Deposit",
            account_name="Stocks", provider="manual",
            source="manual_investment_transactions",
            category="Investments", tag="Stocks",
        ))
        # Legacy consolidated offset row that must be deleted.
        db_session.add(ManualInvestmentTransaction(
            id="2", date="2024-01-01", amount=1000.0, description="Prior Wealth",
            account_name="Prior Wealth", provider="manual",
            source="manual_investment_transactions",
            category="Other Income", tag="Prior Wealth",
        ))
        db_session.commit()

        mig = _load_migration()
        ctx = MigrationContext.configure(db_session.connection())
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()  # second run must be a no-op, not an error

        db_session.expire_all()
        refreshed = db_session.query(Investment).one()
        assert refreshed.prior_wealth_amount == 1000.0

        remaining = db_session.query(ManualInvestmentTransaction).all()
        assert [t.id for t in remaining] == ["1"]
