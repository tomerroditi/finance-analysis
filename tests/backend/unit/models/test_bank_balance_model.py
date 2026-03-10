"""
Unit tests for BankBalance ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.bank_balance import BankBalance


class TestBankBalance:
    """Tests for BankBalance model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert BankBalance.__tablename__ == Tables.BANK_BALANCES.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated and persisted with all fields."""
        balance = BankBalance(
            provider="hapoalim",
            account_name="Main Account",
            balance=50000.0,
            prior_wealth_amount=20000.0,
            last_manual_update="2026-02-13",
            last_scrape_update="2026-02-13",
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.id is not None
        assert balance.provider == "hapoalim"
        assert balance.balance == 50000.0
        assert balance.prior_wealth_amount == 20000.0

    def test_default_prior_wealth(self, db_session: Session):
        """Test that prior_wealth_amount defaults to 0.0."""
        balance = BankBalance(
            provider="leumi",
            account_name="Savings",
            balance=10000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.prior_wealth_amount == 0.0

    def test_nullable_date_fields(self, db_session: Session):
        """Test that date fields can be None."""
        balance = BankBalance(
            provider="discount",
            account_name="Checking",
            balance=5000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.last_manual_update is None
        assert balance.last_scrape_update is None

    def test_timestamp_mixin(self, db_session: Session):
        """Test that created_at and updated_at are auto-populated."""
        balance = BankBalance(
            provider="mizrahi",
            account_name="Joint",
            balance=30000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.created_at is not None
        assert balance.updated_at is not None
