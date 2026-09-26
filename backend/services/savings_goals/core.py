"""Business logic for savings goals.

A goal is a **virtual earmark** over money already sitting in tracked accounts,
never an addition to net worth. Progress is derived rather than typed:

1. Each month's *realized surplus* is computed from transactions —
   ``income - expenses - investments``, credit-card-deduped exactly like the
   rest of the analysis layer (see ``.claude/rules/kpi_calculations.md``).
2. Transactions attached to a goal are excluded from that surplus and handled
   explicitly, so every shekel is counted once: a **contribution** consumes the
   month's pool before the waterfall runs, and a **utilization** (money spent
   back out of a goal) reduces the goal's available balance without touching
   the pool — it was set aside in an earlier month.
3. Whatever is left flows down the goals by ``priority``, each taking up to
   ``min(remaining need, monthly_cap)`` and spilling the rest to the next goal.
4. Whatever *still* remains lands in the **free-cash pool** — the tracked
   money no goal has earmarked. A month that spends more than it earns drains
   that pool first, and only claws money back out of goals (lowest priority
   first, never below what a goal has already spent) once the pool is empty.

A goal can also be backed by an **investment** the user means to liquidate
(bonds earmarked for a car). That backing is valued live from the holding, so
it counts toward the goal's progress and shrinks what the goal still needs from
surplus — but it is not cash: it never enters the free-cash pool and a deficit
month can never claw it back.

Results are persisted per (goal, month) in ``savings_goal_allocations``. Past
months are never silently restated: a priority change applies going forward,
and rewriting history is an explicit ``rebuild`` the user previews first. Goals
that have been closed are frozen — their allocations are replayed as-is and can
never be pulled back out, even by a rebuild.

The service is split across mixins: ``inputs`` (context and pool inputs),
``engine`` (simulation, persistence, rebuild), ``goals`` (CRUD and
transaction links), ``backings`` (investment earmarks) and ``read_models``
(enriched goals, month view, free cash, timeline).
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.repositories.savings_goal_repository import SavingsGoalRepository
from backend.services.savings_goals.backings import InvestmentBackingMixin
from backend.services.savings_goals.engine import AllocationEngineMixin, AllocationPlan
from backend.services.savings_goals.goals import GoalCrudMixin
from backend.services.savings_goals.inputs import InputsMixin
from backend.services.savings_goals.read_models import ReadModelsMixin
from backend.services.transactions_service import TransactionsService


class SavingsGoalService(
    ReadModelsMixin,
    GoalCrudMixin,
    InvestmentBackingMixin,
    AllocationEngineMixin,
    InputsMixin,
):
    """Manage savings goals and distribute each month's surplus across them.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SavingsGoalRepository(db)
        self.transactions_service = TransactionsService(db)
        # Building the context scans every transaction, and a single request
        # needs it more than once (the allocation pass, then the enrichment).
        # The service is constructed per request, so caching it here is
        # request-scoped and never goes stale mid-call.
        self._context_cache: dict[str, Any] | None = None
        # The last simulation pass, kept so the free-cash pool and the
        # per-month deficit figures can be read back without walking the
        # whole timeline a second time.
        self._last_plan: AllocationPlan | None = None
        # Investment earmarks are valued live off each holding's balance, and
        # one request needs them repeatedly (allocating, then enriching).
        self._backing_cache: dict[int, float] | None = None
        # A waterfall order not yet written: a reorder simulates under it
        # first and only then persists it, together with the ledger, in one
        # short transaction (see ``rebuild``).
        self._order_override: list[int] | None = None
