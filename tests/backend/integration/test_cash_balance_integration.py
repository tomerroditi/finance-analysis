"""
Integration tests for cash balance with transaction lifecycle.
"""

from datetime import datetime

import pytest

from backend.services.cash_balance_service import CashBalanceService
from backend.services.transactions_service import TransactionsService


class TestCashBalanceIntegration:
    """Integration tests for cash balance and transactions together."""

    @pytest.fixture
    def cash_service(self, db_session):
        """Create cash service."""
        return CashBalanceService(db_session)

    @pytest.fixture
    def txn_service(self, db_session):
        """Create transactions service."""
        return TransactionsService(db_session)

    def test_cash_transaction_updates_balance_automatically(
        self, cash_service, txn_service
    ):
        """
        When user sets balance and then adds transactions,
        balance auto-updates but prior_wealth stays fixed.
        """
        # Set initial balance: no transactions yet
        cash_service.set_balance("Wallet", 500.0)

        # Verify initial state
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 500.0
        assert record["prior_wealth_amount"] == 500.0

        # Add a -50 transaction
        txn_service.create_transaction(
            data={
                "date": datetime(2026, 2, 1).date(),
                "provider": "manual",
                "account_name": "Wallet",
                "description": "Coffee",
                "amount": -50.0,
            },
            service="cash",
        )

        # Verify balance updated, prior_wealth unchanged
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 450.0  # 500 + (-50)
        assert record["prior_wealth_amount"] == 500.0

    def test_deleting_cash_transaction_updates_balance(
        self, cash_service, txn_service, db_session
    ):
        """
        When a cash transaction is deleted, balance auto-recalculates.
        """
        # Set balance with no transactions first
        cash_service.set_balance("Wallet", 500.0)

        # Verify initial state: prior_wealth = balance - sum(txns) = 500 - 0 = 500
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 500.0
        prior_wealth_fixed = record["prior_wealth_amount"]
        assert prior_wealth_fixed == 500.0

        # Add a -50 transaction
        txn_service.create_transaction(
            data={
                "date": datetime(2026, 2, 1).date(),
                "provider": "manual",
                "account_name": "Wallet",
                "description": "Coffee",
                "amount": -50.0,
            },
            service="cash",
        )

        # Verify balance updated but prior_wealth stays fixed
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 450.0  # 500 + (-50)
        assert record["prior_wealth_amount"] == prior_wealth_fixed

        # Get the transaction ID to delete
        df = txn_service.get_all_transactions(service="cash")
        # Filter out Prior Wealth transactions (tag == "Prior Wealth")
        df_manual = df[df["tag"] != "Prior Wealth"]
        assert len(df_manual) == 1, f"Expected 1 manual transaction, got {len(df_manual)}"
        txn_id = df_manual.iloc[0]["id"]

        # Delete the transaction
        txn_service.delete_transaction(unique_id=int(txn_id), source="cash_transactions")

        # Balance should recalculate back to prior_wealth
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 500.0
        assert record["prior_wealth_amount"] == prior_wealth_fixed
