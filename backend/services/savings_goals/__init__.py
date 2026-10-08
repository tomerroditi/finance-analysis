"""
Savings-goal service package.

Modules:

- ``common`` — shared constants and pure month helpers.
- ``inputs`` — goals in waterfall order, the transaction context (surplus and
  goal-linked amounts) and the pre-goal pool.
- ``engine`` — the surplus waterfall simulation, clawback, ledger persistence
  and ``rebuild``.
- ``goals`` — goal CRUD and transaction links.
- ``read_models`` — enriched goals, the month view, free cash and timeline.
- ``core`` — the public ``SavingsGoalService`` class assembling the mixins.
"""

from backend.services.savings_goals.common import ROUNDING_EPSILON
from backend.services.savings_goals.core import SavingsGoalService
from backend.services.savings_goals.read_models import DAYS_PER_MONTH

__all__ = ["DAYS_PER_MONTH", "ROUNDING_EPSILON", "SavingsGoalService"]
