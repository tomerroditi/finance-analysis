"""Tests for OnboardingService."""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.services.onboarding_service import OnboardingService


class TestOnboardingService:
    """Tests for OnboardingService.get_status."""

    @pytest.fixture
    def service(self, db_session: Session):
        """Create an OnboardingService instance."""
        return OnboardingService(db_session)

    def test_empty_database_is_first_run(self, service):
        """Empty DB returns all flags false and is_first_run true."""
        status = service.get_status()
        assert status == {
            "has_credentials": False,
            "has_transactions": False,
            "has_budgets": False,
            "has_investments": False,
            "is_first_run": True,
        }

    def test_bank_transaction_flips_has_transactions(
        self, service, db_session: Session
    ):
        """Inserting any bank transaction flips has_transactions."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(
                f"""
                INSERT INTO {Tables.BANK.value}
                (id, date, amount, description, account_name, provider, source,
                 created_at, updated_at)
                VALUES ('t1', '2026-01-01', -50, 'X', 'Main', 'hapoalim',
                        'bank_transactions', '{now}', '{now}')
                """
            )
        )
        db_session.commit()
        status = service.get_status()
        assert status["has_transactions"] is True
        assert status["is_first_run"] is False

    def test_credit_card_transaction_flips_has_transactions(
        self, service, db_session: Session
    ):
        """Credit card transactions also count toward has_transactions."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(
                f"""
                INSERT INTO {Tables.CREDIT_CARD.value}
                (id, date, amount, description, account_name, provider, source,
                 created_at, updated_at)
                VALUES ('t1', '2026-01-01', -50, 'X', 'CC', 'isracard',
                        'credit_card_transactions', '{now}', '{now}')
                """
            )
        )
        db_session.commit()
        status = service.get_status()
        assert status["has_transactions"] is True
        assert status["is_first_run"] is False

    def test_budget_rule_flips_has_budgets(self, service, db_session: Session):
        """A budget rule flips has_budgets and clears is_first_run."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(
                f"""
                INSERT INTO {Tables.BUDGET_RULES.value}
                (category, tags, amount, year, month, created_at, updated_at)
                VALUES ('Food', 'Groceries', 1000, 2026, 1, '{now}', '{now}')
                """
            )
        )
        db_session.commit()
        status = service.get_status()
        assert status["has_budgets"] is True
        assert status["is_first_run"] is False

    def test_investment_flips_has_investments(
        self, service, db_session: Session
    ):
        """An investment row flips has_investments and clears is_first_run."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(
                f"""
                INSERT INTO {Tables.INVESTMENTS.value}
                (category, tag, type, name, is_closed, created_date,
                 prior_wealth_amount, created_at, updated_at)
                VALUES ('Investments', 'Stocks', 'stocks', 'Test', 0,
                        '2026-01-01', 0.0, '{now}', '{now}')
                """
            )
        )
        db_session.commit()
        status = service.get_status()
        assert status["has_investments"] is True
        assert status["is_first_run"] is False

    def test_credential_flips_has_credentials(self, service, db_session: Session):
        """A stored credential row flips has_credentials and clears is_first_run."""
        now = datetime.now().isoformat()
        db_session.execute(
            text(
                f"""
                INSERT INTO {Tables.CREDENTIALS.value}
                (service, provider, account_name, fields, created_at, updated_at)
                VALUES ('banks', 'hapoalim', 'main', '{{}}', '{now}', '{now}')
                """
            )
        )
        db_session.commit()
        status = service.get_status()
        assert status["has_credentials"] is True
        assert status["is_first_run"] is False
