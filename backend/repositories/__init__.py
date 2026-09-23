"""
Backend Repositories

This package contains refactored repository classes with pure SQLAlchemy.
"""

from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.transactions_repository import (
    BankRepository,
    CashRepository,
    CashTransaction,
    CreditCardRepository,
    ManualInvestmentTransaction,
    ManualInvestmentTransactionsRepository,
    TransactionsRepository,
)

try:
    from backend.repositories.credentials_repository import CredentialsRepository
except ImportError:
    CredentialsRepository = None  # type: ignore[assignment,misc]
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.tagging_rules_repository import TaggingRulesRepository

__all__ = [
    "BankRepository",
    "BudgetRepository",
    "CashRepository",
    "CashTransaction",
    "CredentialsRepository",
    "CreditCardRepository",
    "InvestmentsRepository",
    "ManualInvestmentTransaction",
    "ManualInvestmentTransactionsRepository",
    "ScrapingHistoryRepository",
    "SplitTransactionsRepository",
    "TaggingRepository",
    "TaggingRulesRepository",
    "TransactionsRepository",
]
