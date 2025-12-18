"""
Backend Repositories

This package contains refactored repository classes with pure SQLAlchemy.
"""
from backend.repositories.transactions_repository import (
    TransactionsRepository,
    CreditCardRepository,
    BankRepository,
    CashRepository,
    ManualInvestmentTransactionsRepository,
    CashTransaction,
    ManualInvestmentTransaction,
)
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.split_transactions_repository import SplitTransactionsRepository

__all__ = [
    "TransactionsRepository",
    "CreditCardRepository",
    "BankRepository",
    "CashRepository",
    "ManualInvestmentTransactionsRepository",
    "CashTransaction",
    "ManualInvestmentTransaction",
    "BudgetRepository",
    "TaggingRepository",
    "CredentialsRepository",
    "ScrapingHistoryRepository",
    "InvestmentsRepository",
    "TaggingRulesRepository",
    "SplitTransactionsRepository",
]
