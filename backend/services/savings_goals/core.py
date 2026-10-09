"""Business logic for savings goals.

A goal is a **virtual earmark** over money already sitting in the tracked bank
and cash accounts, never an addition to net worth. A goal holds:

- the money the user put into it or took out of it (``savings_goal_entries``),
- plus income its "saved into" rule or income links claim,
- less spending its spending rule or links pay for.

Nothing is distributed automatically and nothing restates the past. **Free
cash** is the bank and cash money no goal holds; when goals hold more than
there is, it goes negative and the user covers it — one click applies a plan
that takes the shortfall back from the lowest goals first.

The service is split across mixins: ``inputs`` (goals and everything read off
transactions), ``ledger`` (each goal's balance and free cash, month by month),
``goals`` (CRUD, money in and out, fund, cover, links), ``read_models`` (the
goal list, free cash, timeline and month view) and ``yearly`` (how much each
year saved against its target — measured from the same transactions).
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.repositories.savings_goal_repository import SavingsGoalRepository
from backend.services.savings_goals.goals import GoalCrudMixin
from backend.services.savings_goals.inputs import InputsMixin
from backend.services.savings_goals.ledger import Ledger, LedgerMixin
from backend.services.savings_goals.read_models import ReadModelsMixin
from backend.services.savings_goals.yearly import YearlySavingsMixin
from backend.services.transactions_service import TransactionsService


class SavingsGoalService(
    YearlySavingsMixin,
    ReadModelsMixin,
    GoalCrudMixin,
    LedgerMixin,
    InputsMixin,
):
    """Manage savings goals: what each holds, and the free cash beside them.

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
        # reads it more than once. The service is constructed per request, so
        # these caches are request-scoped; every write drops them.
        self._context_cache: dict[str, Any] | None = None
        self._ledger_cache: Ledger | None = None
