"""
Unit tests for BankBalanceRepository.
"""

from sqlalchemy.orm import Session

from backend.repositories.bank_balance_repository import BankBalanceRepository


class TestBankBalanceRepository:
    """Tests for BankBalanceRepository."""

    def test_get_all_empty(self, db_session: Session):
        """Get all returns empty DataFrame when no records exist."""
        repo = BankBalanceRepository(db_session)
        result = repo.get_all()
        assert result.empty

    def test_upsert_creates_new_record(self, db_session: Session):
        """Upsert creates a new record when none exists."""
        repo = BankBalanceRepository(db_session)
        record = repo.upsert(
            provider="hapoalim",
            account_name="Main",
            balance=50000.0,
            prior_wealth_amount=20000.0,
            last_manual_update="2026-02-13",
        )
        assert record.id is not None
        assert record.balance == 50000.0
        assert record.prior_wealth_amount == 20000.0

    def test_upsert_updates_existing_record(self, db_session: Session):
        """Upsert updates an existing record for the same account."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0, last_manual_update="2026-02-13")
        repo.upsert("hapoalim", "Main", 55000.0, 20000.0, last_scrape_update="2026-02-14")
        record = repo.get_by_account("hapoalim", "Main")
        assert record.balance == 55000.0
        assert record.last_manual_update == "2026-02-13"
        assert record.last_scrape_update == "2026-02-14"

    def test_get_by_account_not_found(self, db_session: Session):
        """Get by account returns None when not found."""
        repo = BankBalanceRepository(db_session)
        result = repo.get_by_account("nonexistent", "nope")
        assert result is None

    def test_get_all_returns_dataframe(self, db_session: Session):
        """Get all returns a DataFrame with all records."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0)
        repo.upsert("leumi", "Savings", 30000.0, 10000.0)
        result = repo.get_all()
        assert len(result) == 2
        assert "provider" in result.columns
        assert "balance" in result.columns

    def test_delete_by_account(self, db_session: Session):
        """Delete removes the record and returns True."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0)
        deleted = repo.delete_by_account("hapoalim", "Main")
        assert deleted is True
        assert repo.get_by_account("hapoalim", "Main") is None

    def test_delete_by_account_not_found(self, db_session: Session):
        """Delete returns False when record does not exist."""
        repo = BankBalanceRepository(db_session)
        deleted = repo.delete_by_account("nonexistent", "nope")
        assert deleted is False
