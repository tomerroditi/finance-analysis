"""Unit tests for CashBalanceService functionality."""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from backend.services.cash_balance_service import CashBalanceService
from backend.models.cash_balance import CashBalance
from backend.models.transaction import CashTransaction


class TestCashBalanceService:
    """Tests for CashBalanceService functionality."""

    def test_set_balance_with_no_transactions(self, db_session: Session):
        """Verify set_balance with no transactions calculates prior_wealth = balance.

        When there are no cash transactions, prior_wealth should equal the balance.
        """
        service = CashBalanceService(db_session)

        result = service.set_balance("Main Wallet", 1000.0)

        assert result["account_name"] == "Main Wallet"
        assert result["balance"] == 1000.0
        assert result["prior_wealth_amount"] == 1000.0

        # Verify it's persisted
        retrieved = service.get_by_account_name("Main Wallet")
        assert retrieved is not None
        assert retrieved["balance"] == 1000.0
        assert retrieved["prior_wealth_amount"] == 1000.0

    def test_set_balance_with_existing_transactions(self, db_session: Session):
        """Verify set_balance calculates prior_wealth = balance - sum(transactions).

        prior_wealth is calculated as: balance - sum of all cash transactions
        """
        # Add cash transactions summing to -200
        txn1 = CashTransaction(
            id="cash_1",
            date="2024-01-01",
            account_name="Main Wallet",
            description="Expense 1",
            amount=-100.0,
            category="Food",
            tag="Groceries",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        txn2 = CashTransaction(
            id="cash_2",
            date="2024-01-02",
            account_name="Main Wallet",
            description="Expense 2",
            amount=-100.0,
            category="Transport",
            tag="Gas",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        db_session.add_all([txn1, txn2])
        db_session.commit()

        service = CashBalanceService(db_session)

        # Set balance to 800 (prior_wealth should be 800 - (-200) = 1000)
        result = service.set_balance("Main Wallet", 800.0)

        assert result["balance"] == 800.0
        assert result["prior_wealth_amount"] == 1000.0

    def test_set_balance_rejects_negative_balance(self, db_session: Session):
        """Verify set_balance rejects negative balance values."""
        service = CashBalanceService(db_session)

        with pytest.raises(ValueError, match="Balance must be >= 0"):
            service.set_balance("Main Wallet", -100.0)

    def test_recalculate_current_balance_updates_balance_keeps_prior_wealth(
        self, db_session: Session
    ):
        """Verify recalculate_current_balance updates balance but keeps prior_wealth fixed.

        When recalculating, prior_wealth should remain the same while balance is updated.
        """
        # Add initial cash transaction
        txn1 = CashTransaction(
            id="cash_1",
            date="2024-01-01",
            account_name="Main Wallet",
            description="Expense 1",
            amount=-100.0,
            category="Food",
            tag="Groceries",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        db_session.add(txn1)
        db_session.commit()

        service = CashBalanceService(db_session)

        # Set initial balance to 900 (prior_wealth = 900 - (-100) = 1000)
        service.set_balance("Main Wallet", 900.0)

        # Add new transaction
        txn2 = CashTransaction(
            id="cash_2",
            date="2024-01-02",
            account_name="Main Wallet",
            description="Expense 2",
            amount=-50.0,
            category="Transport",
            tag="Gas",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        db_session.add(txn2)
        db_session.commit()

        # Recalculate: balance should be prior_wealth + sum(txns) = 1000 + (-150) = 850
        # but prior_wealth should stay 1000
        result = service.recalculate_current_balance("Main Wallet")

        assert result["balance"] == 850.0
        assert result["prior_wealth_amount"] == 1000.0

    def test_get_all_balances(self, db_session: Session):
        """Verify get_all_balances returns list of balance dicts."""
        service = CashBalanceService(db_session)

        service.set_balance("Wallet 1", 500.0)
        service.set_balance("Wallet 2", 1000.0)

        result = service.get_all_balances()

        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

        names = {r["account_name"] for r in result}
        assert names == {"Wallet 1", "Wallet 2"}

    def test_get_by_account_name(self, db_session: Session):
        """Verify get_by_account_name returns balance dict or None."""
        service = CashBalanceService(db_session)

        service.set_balance("Main Wallet", 750.0)

        result = service.get_by_account_name("Main Wallet")

        assert result is not None
        assert result["account_name"] == "Main Wallet"
        assert result["balance"] == 750.0

        # Non-existent account
        result = service.get_by_account_name("Unknown")
        assert result is None

    def test_get_total_prior_wealth(self, db_session: Session):
        """Verify get_total_prior_wealth sums prior_wealth across all accounts."""
        service = CashBalanceService(db_session)

        service.set_balance("Wallet 1", 500.0)
        service.set_balance("Wallet 2", 1000.0)

        total = service.get_total_prior_wealth()

        assert total == 1500.0

    def test_delete_for_account(self, db_session: Session):
        """Verify delete_for_account removes the balance record."""
        service = CashBalanceService(db_session)

        service.set_balance("Main Wallet", 500.0)

        # Verify it exists
        result = service.get_by_account_name("Main Wallet")
        assert result is not None

        # Delete it
        service.delete_for_account("Main Wallet")

        # Verify it's gone
        result = service.get_by_account_name("Main Wallet")
        assert result is None
