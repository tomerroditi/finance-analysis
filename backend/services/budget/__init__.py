"""
Budget services package.

The budget domain is split along class boundaries:

- ``core`` — ``BudgetService``: rule CRUD, tag parsing, validation,
  cross-kind conflict helpers, shared copy engine, expense filtering.
- ``monthly`` — ``MonthlyBudgetService``: month-scoped rules, auto-fill,
  monthly analysis/views/alerts.
- ``yearly`` — ``YearlyBudgetService``: per-year envelopes, carry-forward.
- ``project`` — ``ProjectBudgetService``: time-unbounded project budgets.

``backend.services.budget_service`` remains as a compatibility shim
re-exporting these names.
"""

from backend.services.budget.core import BudgetService, _auto_fill_lock, _today
from backend.services.budget.monthly import MonthlyBudgetService
from backend.services.budget.project import ProjectBudgetService
from backend.services.budget.yearly import YearlyBudgetService

__all__ = [
    "BudgetService",
    "MonthlyBudgetService",
    "ProjectBudgetService",
    "YearlyBudgetService",
    "_auto_fill_lock",
    "_today",
]
