"""Unit tests for CashBalanceService functionality."""

import pytest
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
        """Verify delete_for_account removes the balance record and migrates transactions."""
        service = CashBalanceService(db_session)

        # Create both Wallet (default) and another account
        service.set_balance("Wallet", 0.0)
        service.set_balance("Savings", 500.0)

        # Add a transaction to Savings
        txn = CashTransaction(
            id="cash_del_1",
            date="2024-01-01",
            account_name="Savings",
            description="Test",
            amount=-100.0,
            category="Food",
            tag="Groceries",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        db_session.add(txn)
        db_session.commit()

        # Delete Savings — transactions should migrate to Wallet
        service.delete_for_account("Savings")

        # Verify Savings is gone
        assert service.get_by_account_name("Savings") is None

        # Verify the transaction moved to Wallet
        db_session.expire_all()
        migrated_txn = db_session.query(CashTransaction).filter_by(
            id="cash_del_1"
        ).first()
        assert migrated_txn.account_name == "Wallet"

    def test_delete_wallet_raises_error(self, db_session: Session):
        """Verify delete_for_account prevents deletion of the default Wallet account."""
        service = CashBalanceService(db_session)
        service.set_balance("Wallet", 500.0)

        with pytest.raises(ValueError, match="Cannot delete the default 'Wallet' account"):
            service.delete_for_account("Wallet")

        # Verify it still exists
        result = service.get_by_account_name("Wallet")
        assert result is not None

    def test_delete_for_account_recalculates_wallet_balance(self, db_session: Session):
        """Verify deleting an account recalculates the Wallet balance after migration.

        When transactions are migrated from a deleted account to Wallet,
        Wallet's balance should be recalculated to include those transactions.
        """
        service = CashBalanceService(db_session)

        # Set up Wallet with prior_wealth=1000, no transactions → balance=1000
        service.set_balance("Wallet", 1000.0)
        # Set up Savings with prior_wealth=500, no transactions → balance=500
        service.set_balance("Savings", 500.0)

        # Add a -200 transaction to Savings
        txn = CashTransaction(
            id="cash_recalc_1",
            date="2024-01-01",
            account_name="Savings",
            description="Expense",
            amount=-200.0,
            category="Food",
            tag="Groceries",
            source="cash_transactions",
            type="expense",
            status="completed",
        )
        db_session.add(txn)
        db_session.commit()

        # Delete Savings — its -200 transaction migrates to Wallet
        service.delete_for_account("Savings")

        # Wallet balance should be recalculated: prior_wealth(1000) + txn_sum(-200) = 800
        wallet = service.get_by_account_name("Wallet")
        assert wallet["balance"] == 800.0
        assert wallet["prior_wealth_amount"] == 1000.0


class TestMigrateFromTransactions:
    """Tests for migrate_from_transactions() migration logic."""

    def test_migrate_empty_transactions(self, db_session: Session):
        """Verify migration returns empty list when no cash transactions exist."""
        service = CashBalanceService(db_session)
        result = service.migrate_from_transactions()
        assert result == []

    def test_migrate_creates_balance_records(self, db_session: Session):
        """Verify migration creates balance records from existing transactions."""
        # Add transactions for two accounts
        txns = [
            CashTransaction(
                id="m1", date="2024-01-01", account_name="Wallet",
                description="Expense", amount=-300.0, category="Food",
                tag="Groceries", source="cash_transactions",
                type="expense", status="completed",
            ),
            CashTransaction(
                id="m2", date="2024-01-02", account_name="Wallet",
                description="Income", amount=100.0, category="Salary",
                tag="", source="cash_transactions",
                type="income", status="completed",
            ),
            CashTransaction(
                id="m3", date="2024-01-01", account_name="Savings",
                description="Expense", amount=-500.0, category="Food",
                tag="Groceries", source="cash_transactions",
                type="expense", status="completed",
            ),
        ]
        db_session.add_all(txns)
        db_session.commit()

        service = CashBalanceService(db_session)
        result = service.migrate_from_transactions()

        assert len(result) == 2
        names = {r["account_name"] for r in result}
        assert names == {"Wallet", "Savings"}

        # Wallet: txn_sum=-200, prior_wealth=max(0, 200)=200, balance=200+(-200)=0
        wallet = next(r for r in result if r["account_name"] == "Wallet")
        assert wallet["prior_wealth_amount"] == 200.0
        assert wallet["balance"] == 0.0

        # Savings: txn_sum=-500, prior_wealth=max(0, 500)=500, balance=500+(-500)=0
        savings = next(r for r in result if r["account_name"] == "Savings")
        assert savings["prior_wealth_amount"] == 500.0
        assert savings["balance"] == 0.0

    def test_migrate_net_positive_transactions(self, db_session: Session):
        """Verify migration sets prior_wealth=0 when transaction sum is positive."""
        txn = CashTransaction(
            id="m_pos", date="2024-01-01", account_name="Wallet",
            description="Income", amount=500.0, category="Salary",
            tag="", source="cash_transactions",
            type="income", status="completed",
        )
        db_session.add(txn)
        db_session.commit()

        service = CashBalanceService(db_session)
        result = service.migrate_from_transactions()

        assert len(result) == 1
        assert result[0]["prior_wealth_amount"] == 0.0
        assert result[0]["balance"] == 500.0

    def test_migrate_skips_already_migrated_accounts(self, db_session: Session):
        """Verify migration skips accounts that already have balance records."""
        # Pre-create a balance record
        db_session.add(CashBalance(
            account_name="Wallet", balance=1000.0, prior_wealth_amount=1000.0,
        ))
        txn = CashTransaction(
            id="m_skip", date="2024-01-01", account_name="Wallet",
            description="Expense", amount=-100.0, category="Food",
            tag="Groceries", source="cash_transactions",
            type="expense", status="completed",
        )
        db_session.add(txn)
        db_session.commit()

        service = CashBalanceService(db_session)
        result = service.migrate_from_transactions()

        assert result == []

    def test_migrate_excludes_prior_wealth_account(self, db_session: Session):
        """Verify migration excludes transactions with account_name='Prior Wealth'."""
        txns = [
            CashTransaction(
                id="m_pw", date="2024-01-01", account_name="Prior Wealth",
                description="Prior Wealth", amount=1000.0, category="",
                tag="Prior Wealth", source="cash_transactions",
                type="income", status="completed",
            ),
            CashTransaction(
                id="m_real", date="2024-01-01", account_name="Wallet",
                description="Expense", amount=-50.0, category="Food",
                tag="Groceries", source="cash_transactions",
                type="expense", status="completed",
            ),
        ]
        db_session.add_all(txns)
        db_session.commit()

        service = CashBalanceService(db_session)
        result = service.migrate_from_transactions()

        # Only Wallet should be migrated, not "Prior Wealth"
        assert len(result) == 1
        assert result[0]["account_name"] == "Wallet"


class TestDeletePriorWealthTransaction:
    """Tests for _delete_prior_wealth_transaction() cleanup."""

    def test_deletes_matching_prior_wealth_row(self, db_session: Session):
        """Verify only Prior Wealth rows with matching tag and account_name are deleted."""
        txns = [
            CashTransaction(
                id="pw_del", date="2024-01-01", account_name="Prior Wealth",
                description="Prior Wealth", amount=1000.0, category="",
                tag="Prior Wealth", source="cash_transactions",
                type="income", status="completed",
            ),
            CashTransaction(
                id="normal", date="2024-01-01", account_name="Wallet",
                description="Groceries", amount=-50.0, category="Food",
                tag="Groceries", source="cash_transactions",
                type="expense", status="completed",
            ),
        ]
        db_session.add_all(txns)
        db_session.commit()

        service = CashBalanceService(db_session)
        service._delete_prior_wealth_transaction()

        remaining = db_session.query(CashTransaction).all()
        assert len(remaining) == 1
        assert remaining[0].id == "normal"

    def test_noop_when_no_prior_wealth_exists(self, db_session: Session):
        """Verify no error when there's nothing to delete."""
        service = CashBalanceService(db_session)
        service._delete_prior_wealth_transaction()  # Should not raise
