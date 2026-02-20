"""Tests for TransactionsRepository delegation to sub-repositories."""

from datetime import datetime

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from backend.models.transaction import CashTransaction
from backend.repositories.transactions_repository import (
    TransactionsRepository,
    CreditCardRepository,
    BankRepository,
    CashRepository,
    ManualInvestmentTransactionsRepository,
    ManualTransactionDTO,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def transactions_repo(mock_db):
    """Create a TransactionsRepository with mocked sub-repositories."""
    repo = TransactionsRepository(mock_db)
    repo.cc_repo = MagicMock(spec=CreditCardRepository)
    repo.bank_repo = MagicMock(spec=BankRepository)
    repo.cash_repo = MagicMock(spec=CashRepository)
    repo.manual_investments_repo = MagicMock(
        spec=ManualInvestmentTransactionsRepository
    )
    return repo


class TestTransactionsRepositoryDelegation:
    """Tests for TransactionsRepository delegating operations to all sub-repositories."""

    def test_nullify_category(self, transactions_repo):
        """Verify nullify_category delegates to all four sub-repositories."""
        transactions_repo.nullify_category("Groceries")

        transactions_repo.cc_repo.nullify_category.assert_called_once_with("Groceries")
        transactions_repo.bank_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )
        transactions_repo.cash_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )
        transactions_repo.manual_investments_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )

    def test_nullify_category_and_tag(self, transactions_repo):
        """Verify nullify_category_and_tag delegates to all four sub-repositories."""
        transactions_repo.nullify_category_and_tag("Entertainment", "Cinema")

        transactions_repo.cc_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.bank_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.cash_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.manual_investments_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )

    def test_update_category_for_tag(self, transactions_repo):
        """Verify update_category_for_tag delegates to all four sub-repositories."""
        transactions_repo.update_category_for_tag("OldCat", "NewCat", "SomeTag")

        transactions_repo.cc_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.bank_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.cash_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.manual_investments_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )


class TestAddTransactionIdGeneration:
    """Tests for ServiceRepository.add_transaction generating IDs via ORM."""

    def test_add_transaction_generates_id_from_max(self, db_session):
        """Verify new transaction gets MAX(existing_id) + 1."""
        # Seed some existing transactions with string IDs
        db_session.add_all([
            CashTransaction(
                id="5", date="2024-01-01", amount=-10.0,
                description="Existing 1", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
            CashTransaction(
                id="12", date="2024-01-02", amount=-20.0,
                description="Existing 2", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
        ])
        db_session.commit()

        repo = CashRepository(db_session)
        dto = ManualTransactionDTO(
            date=datetime(2024, 2, 1),
            account_name="Cash",
            description="New Entry",
            amount=-30.0,
            provider="manual",
        )
        result = repo.add_transaction(dto)

        assert result is True

        # New transaction should have id "13" (MAX(12) + 1)
        df = repo.get_table()
        new_row = df[df["description"] == "New Entry"]
        assert len(new_row) == 1
        assert new_row.iloc[0]["id"] == "13"

    def test_add_transaction_first_entry_gets_id_1(self, db_session):
        """Verify first transaction in empty table gets id '1'."""
        repo = CashRepository(db_session)
        dto = ManualTransactionDTO(
            date=datetime(2024, 3, 1),
            account_name="Cash",
            description="First Entry",
            amount=-5.0,
            provider="manual",
        )
        result = repo.add_transaction(dto)

        assert result is True

        df = repo.get_table()
        assert len(df) == 1
        assert df.iloc[0]["id"] == "1"
