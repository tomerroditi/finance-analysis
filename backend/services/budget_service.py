"""
Compatibility shim — the budget services now live in ``backend.services.budget``.

Kept so existing ``from backend.services.budget_service import X`` imports keep
working. New code should import from ``backend.services.budget`` (or its
submodules ``core``, ``monthly``, ``yearly``, ``project``) directly.

Note: tests that monkeypatch module-level names (``date``, ``_today``) must
target the defining submodule (e.g. ``backend.services.budget.monthly.date``,
``backend.services.budget.yearly._today``) — patching this shim's re-exports
does not affect the implementation modules.
"""

from backend.services.budget import (
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
    YearlyBudgetService,
    _auto_fill_lock,
    _today,
)

__all__ = [
    "BudgetService",
    "MonthlyBudgetService",
    "ProjectBudgetService",
    "YearlyBudgetService",
    "_auto_fill_lock",
    "_today",
]
