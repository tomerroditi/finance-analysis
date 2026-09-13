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

``backend.services.budget_service`` remains as a compatibility shim
re-exporting these names.
"""

from backend.services.budget.core import BudgetService, _auto_fill_lock, _today
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
    "_auto_fill_lock",
    "_today",
]
