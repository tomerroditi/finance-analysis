"""
Tests for BankBalanceService.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.errors import ValidationException
from backend.services.bank_balance_service import BankBalanceService


class TestBankBalanceService:
    """Tests for BankBalanceService functionality."""

    @pytest.fixture
    def service(self, db_session: Session):
        """Create a BankBalanceService instance."""
        return BankBalanceService(db_session)

    @pytest.fixture
    def setup_bank_transactions(self, db_session: Session):
        """Insert sample bank transactions."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.BANK.value}
            (id, date, amount, description, account_name, provider, source, created_at, updated_at)
            VALUES
            ('txn1', '2026-02-01', -500.0, 'Rent', 'Main', 'hapoalim', 'bank_transactions', '{now}', '{now}'),
            ('txn2', '2026-02-05', 10000.0, 'Salary', 'Main', 'hapoalim', 'bank_transactions', '{now}', '{now}'),
            ('txn3', '2026-02-10', -200.0, 'Groceries', 'Main', 'hapoalim', 'bank_transactions', '{now}', '{now}'),
            ('txn4', '2026-02-10', -100.0, 'Other', 'Savings', 'leumi', 'bank_transactions', '{now}', '{now}')
            """)
        )
        db_session.commit()

    @pytest.fixture
    def setup_scrape_today(self, db_session: Session):
        """Insert a successful scrape record for today."""
        today = date.today().isoformat()
        now = datetime.now().isoformat()
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.SCRAPING_HISTORY.value}
            (service_name, provider_name, account_name, date, status, created_at, updated_at)
            VALUES
            ('banks', 'hapoalim', 'Main', '{today}T10:00:00', 'success', '{now}', '{now}')
            """)
        )
        db_session.commit()

    def test_get_all_balances_empty(self, service: BankBalanceService):
        """Get all balances returns empty list when no records exist."""
        result = service.get_all_balances()
        assert result == []

    def test_set_balance_calculates_prior_wealth(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
    ):
        """Set balance correctly calculates prior wealth from transaction sum."""
        # Txn sum for hapoalim/Main: -500 + 10000 + -200 = 9300
        # Prior wealth = 50000 - 9300 = 40700
        result = service.set_balance("hapoalim", "Main", 50000.0)
        assert result["balance"] == 50000.0
        assert result["prior_wealth_amount"] == 40700.0
        assert result["last_manual_update"] == date.today().isoformat()

    def test_set_balance_rejects_without_today_scrape(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
    ):
        """Set balance raises ValidationException when no scrape today."""
        with pytest.raises(ValidationException):
            service.set_balance("hapoalim", "Main", 50000.0)

    def test_set_balance_rejects_old_scrape(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        db_session: Session,
    ):
        """Set balance raises ValidationException when last scrape is not today."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.SCRAPING_HISTORY.value}
            (service_name, provider_name, account_name, date, status, created_at, updated_at)
            VALUES
            ('banks', 'hapoalim', 'Main', '2026-02-01T10:00:00', 'success', '{now}', '{now}')
            """)
        )
        db_session.commit()
        with pytest.raises(ValidationException):
            service.set_balance("hapoalim", "Main", 50000.0)

    def test_recalculate_updates_balance(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
        db_session: Session,
    ):
        """Recalculate updates balance using fixed prior wealth + new txn sum."""
        service.set_balance("hapoalim", "Main", 50000.0)

        # Add a new transaction (simulating a new scrape)
        now = datetime.now().isoformat()
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.BANK.value}
            (id, date, amount, description, account_name, provider, source, created_at, updated_at)
            VALUES
            ('txn_new', '2026-02-13', -1000.0, 'New expense', 'Main', 'hapoalim', 'bank_transactions', '{now}', '{now}')
            """)
        )
        db_session.commit()

        service.recalculate_for_account("hapoalim", "Main")

        balances = service.get_all_balances()
        assert len(balances) == 1
        # New txn sum: 9300 + (-1000) = 8300
        # New balance: 40700 (prior wealth) + 8300 = 49000
        assert balances[0]["balance"] == 49000.0
        assert balances[0]["prior_wealth_amount"] == 40700.0

    def test_recalculate_noop_without_balance_record(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
    ):
        """Recalculate does nothing when no balance record exists."""
        service.recalculate_for_account("hapoalim", "Main")
        assert service.get_all_balances() == []

    def test_delete_for_account(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
    ):
        """Delete removes balance record for the account."""
        service.set_balance("hapoalim", "Main", 50000.0)
        service.delete_for_account("hapoalim", "Main")
        assert service.get_all_balances() == []

    def test_set_balance_no_transactions(
        self,
        service: BankBalanceService,
        setup_scrape_today,
    ):
        """Set balance when account has no transactions: prior wealth = entered balance."""
        result = service.set_balance("hapoalim", "Main", 50000.0)
        assert result["prior_wealth_amount"] == 50000.0
        assert result["balance"] == 50000.0
