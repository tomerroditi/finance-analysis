"""
Unit tests for CashBalanceRepository operations.
"""

from sqlalchemy.orm import Session

from backend.repositories.cash_balance_repository import CashBalanceRepository


class TestCashBalanceRepository:
    """Tests for CashBalanceRepository CRUD operations."""

    def test_get_all_empty(self, db_session: Session):
        """Verify get_all returns empty DataFrame when no records exist."""
        repo = CashBalanceRepository(db_session)
        result = repo.get_all()
        assert result.empty

    def test_get_by_account_name_not_found(self, db_session: Session):
        """Verify get_by_account_name returns None for nonexistent account."""
        repo = CashBalanceRepository(db_session)
        result = repo.get_by_account_name("Nonexistent")
        assert result is None

    def test_upsert_creates_new_record(self, db_session: Session):
        """Verify upsert creates a new record when none exists."""
        repo = CashBalanceRepository(db_session)
        record = repo.upsert("Main Wallet", 1000.0, 500.0, "2024-01-01")

        assert record.account_name == "Main Wallet"
        assert record.balance == 1000.0
        assert record.prior_wealth_amount == 500.0
        assert record.last_manual_update == "2024-01-01"

        # Verify persisted
        result = repo.get_all()
        assert len(result) == 1

    def test_upsert_updates_existing_record(self, db_session: Session):
        """Verify upsert updates an existing record instead of creating a duplicate."""
        repo = CashBalanceRepository(db_session)

        # Create initial record
        repo.upsert("Main Wallet", 1000.0, 500.0, "2024-01-01")

        # Update it
        updated = repo.upsert("Main Wallet", 800.0, 600.0, "2024-02-01")

        assert updated.balance == 800.0
        assert updated.prior_wealth_amount == 600.0
        assert updated.last_manual_update == "2024-02-01"

        # Verify only one record exists
        result = repo.get_all()
        assert len(result) == 1

    def test_upsert_update_without_manual_date(self, db_session: Session):
        """Verify upsert update preserves last_manual_update when not provided."""
        repo = CashBalanceRepository(db_session)

        # Create with a manual update date
        repo.upsert("Wallet", 1000.0, 500.0, "2024-01-15")

        # Update without providing last_manual_update
        updated = repo.upsert("Wallet", 900.0, 500.0)

        assert updated.balance == 900.0
        assert updated.last_manual_update == "2024-01-15"

    def test_delete_by_account_name_found(self, db_session: Session):
        """Verify delete_by_account_name removes existing record and returns True."""
        repo = CashBalanceRepository(db_session)
        repo.upsert("Wallet", 1000.0, 500.0)

        result = repo.delete_by_account_name("Wallet")

        assert result is True
        assert repo.get_by_account_name("Wallet") is None

    def test_delete_by_account_name_not_found(self, db_session: Session):
        """Verify delete_by_account_name returns False when no record exists."""
        repo = CashBalanceRepository(db_session)

        result = repo.delete_by_account_name("Nonexistent")

        assert result is False

    def test_get_all_multiple_records(self, db_session: Session):
        """Verify get_all returns all records as DataFrame."""
        repo = CashBalanceRepository(db_session)
        repo.upsert("Wallet 1", 500.0, 200.0)
        repo.upsert("Wallet 2", 1000.0, 800.0)
        repo.upsert("Savings", 3000.0, 3000.0)

        result = repo.get_all()
        assert len(result) == 3
        assert set(result["account_name"].tolist()) == {"Wallet 1", "Wallet 2", "Savings"}
