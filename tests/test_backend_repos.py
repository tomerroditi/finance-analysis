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
    return MagicMock(spec=Session)


@pytest.fixture
def transactions_repo(mock_db):
    repo = TransactionsRepository(mock_db)
    # Mock the individual repos to avoid DB calls
    repo.cc_repo = MagicMock(spec=CreditCardRepository)
    repo.bank_repo = MagicMock(spec=BankRepository)
    repo.cash_repo = MagicMock(spec=CashRepository)
    repo.manual_investments_repo = MagicMock(
        spec=ManualInvestmentTransactionsRepository
    )
    return repo


def test_nullify_category(transactions_repo):
    transactions_repo.nullify_category("Groceries")

    transactions_repo.cc_repo.nullify_category.assert_called_once_with("Groceries")
    transactions_repo.bank_repo.nullify_category.assert_called_once_with("Groceries")
    transactions_repo.cash_repo.nullify_category.assert_called_once_with("Groceries")
    transactions_repo.manual_investments_repo.nullify_category.assert_called_once_with(
        "Groceries"
    )


def test_nullify_category_and_tag(transactions_repo):
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


def test_update_category_for_tag(transactions_repo):
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
