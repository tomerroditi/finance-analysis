"""
Backend Services Package

This package contains refactored service classes for the backend.
"""

from backend.services.budget_service import (
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
)
from backend.services.tagging_service import CategoriesTagsService
from backend.services.transactions_service import TransactionsService

__all__ = [
    "BudgetService",
    "CategoriesTagsService",
    "MonthlyBudgetService",
    "ProjectBudgetService",
    "TransactionsService",
]

try:
    from backend.services.credentials_service import CredentialsService  # noqa: F401

    __all__.append("CredentialsService")
except ImportError:
    pass
