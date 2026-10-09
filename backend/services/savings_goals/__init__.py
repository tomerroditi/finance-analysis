"""
Savings-goal service package.

Modules:

- ``common`` — shared constants and pure month helpers.
- ``inputs`` — goals in list order and everything read off transactions.
- ``ledger`` — each goal's balance and free cash, month by month.
- ``goals`` — goal CRUD, money in and out, fund, cover and transaction links.
- ``read_models`` — the goal list, free cash, timeline and month view.
- ``yearly`` — how much each year saved, against its target.
- ``core`` — the public ``SavingsGoalService`` class assembling the mixins.
"""

from backend.services.savings_goals.common import ROUNDING_EPSILON
from backend.services.savings_goals.core import SavingsGoalService
from backend.services.savings_goals.read_models import DAYS_PER_MONTH

__all__ = ["DAYS_PER_MONTH", "ROUNDING_EPSILON", "SavingsGoalService"]
