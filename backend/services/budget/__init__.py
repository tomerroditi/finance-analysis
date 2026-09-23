"""
Budget services package.

The budget domain is split along class boundaries:

- ``core`` — ``BudgetService``: rule CRUD, tag parsing, validation,
  cross-kind conflict helpers, shared copy engine, expense filtering.
- ``monthly`` — ``MonthlyBudgetService``: month-scoped rules, auto-fill,
  monthly analysis/views/alerts.
- ``yearly`` — ``YearlyBudgetService``: per-year envelopes, carry-forward.
- ``project`` — ``ProjectBudgetService``: time-unbounded project budgets.
- ``overview`` — ``BudgetOverviewService``: one month read across all
  three kinds, for the Overview tab.
"""

from backend.services.budget.core import BudgetService
from backend.services.budget.monthly import MonthlyBudgetService
from backend.services.budget.overview import BudgetOverviewService
from backend.services.budget.project import ProjectBudgetService
from backend.services.budget.yearly import YearlyBudgetService

__all__ = [
    "BudgetOverviewService",
    "BudgetService",
    "MonthlyBudgetService",
    "ProjectBudgetService",
    "YearlyBudgetService",
]
