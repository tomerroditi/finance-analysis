"""Tests for TransactionsRepository delegation to sub-repositories."""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from backend.repositories.transactions_repository import (
    TransactionsRepository,
    CreditCardRepository,
    BankRepository,
    CashRepository,
    ManualInvestmentTransactionsRepository,
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
