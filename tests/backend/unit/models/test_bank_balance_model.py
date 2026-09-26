"""
Unit tests for BankBalance ORM model.
"""

from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance


class TestBankBalance:
    """Tests for BankBalance model."""

    def test_defaults_for_optional_fields(self, db_session: Session):
        """prior_wealth_amount defaults to 0.0 and both update dates to None."""
        balance = BankBalance(
            provider="leumi",
            account_name="Savings",
            balance=10000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.prior_wealth_amount == 0.0
        assert balance.last_manual_update is None
        assert balance.last_scrape_update is None
