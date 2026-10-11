"""What each goal holds, and when, for the savings-goal service.

Provides ``LedgerMixin``. A goal's balance is never decided by the app: it is
the money the user put in or took out (``savings_goal_entries``), plus the
income its saved-into rule or links claim, less the spending paid out of it —
replayed in date order. Free cash is what the bank and cash accounts hold less
everything the goals hold. Mixed into ``SavingsGoalService`` (see
``core.py``).

Two rules decide what a goal pays:

- **A goal with income of its own** (a saved-into rule or an income link)
  may spend ahead of that income. Its balance goes negative — ``owed`` — and
  the income repays it as it lands, so bills that come before the gifts are a
  loan from free cash, not an overspend.
- **Any other goal** pays only with what it holds. A bill beyond that comes
  out of free cash for good: the goal stops at zero, and a later deposit is
  new money rather than repaying the bill.
"""

from dataclasses import dataclass, field
from datetime import date

from backend.models.savings_goal import LINK_CONTRIBUTION, SavingsGoal
from backend.services.savings_goals.common import (
    ROUNDING_EPSILON,
    iter_months,
    month_key,
)

#: Same-day order: deposits land first, then income, then the spending that
#: draws on both.
_ORDER = {"entry": 0, "income": 1, "spent": 2}


@dataclass
class GoalState:
    """One goal's running totals at a point in time.

    Attributes
    ----------
    added : float
        Net money the user put in (entries).
    income : float
        Income its rule or links claimed.
    spent : float
        Spending the goal paid. A goal without income of its own never pays
        more than it held, so this can be less than the spending linked to it.
    balance : float
        ``added + income - spent``; negative only for a goal with income of
        its own that spent ahead of it.
    """

    added: float = 0.0
    income: float = 0.0
    spent: float = 0.0
    balance: float = 0.0

    @property
    def available(self) -> float:
        """What the goal holds now: the balance, never below zero."""
        return max(0.0, self.balance)


@dataclass
class Ledger:
    """Every goal replayed from its entries and transactions.

    Attributes
    ----------
    states : dict
        ``{goal_id: GoalState}`` today.
    monthly : dict
        ``{(year, month): {goal_id: GoalState}}`` — each goal's state at the
        end of every month from the first one anything happened in through
        the current month.
    moves : dict
        ``{(year, month): {goal_id: GoalState}}`` — what moved in each month
        alone (``balance`` there is the month's change).
    liquid : dict
        ``{(year, month): float}`` — what the bank and cash accounts held at
        the end of each month in ``monthly``.
    liquid_now : float
        What they hold now.
    """

    states: dict[int, GoalState] = field(default_factory=dict)
    monthly: dict[tuple[int, int], dict[int, GoalState]] = field(default_factory=dict)
    moves: dict[tuple[int, int], dict[int, GoalState]] = field(default_factory=dict)
    liquid: dict[tuple[int, int], float] = field(default_factory=dict)
    liquid_now: float = 0.0

    def free_cash(self, key: tuple[int, int] | None = None) -> float:
        """Return free cash now, or at the end of month ``key``."""
        if key is None:
            held = sum(s.available for s in self.states.values())
            return self.liquid_now - held
        held = sum(s.available for s in self.monthly.get(key, {}).values())
        return self.liquid.get(key, 0.0) - held


class LedgerMixin:
    """Goal balances and free cash for ``SavingsGoalService``."""

    def _ledger(self) -> Ledger:
        """Replay every goal, memoised for the request."""
        if self._ledger_cache is None:
            self._ledger_cache = self._compute_ledger()
        return self._ledger_cache

    def _invalidate(self) -> None:
        """Forget what this request computed, after a write."""
        self._context_cache = None
        self._ledger_cache = None

    def _compute_ledger(self) -> Ledger:
        """Replay entries and goal-linked transactions in date order."""
        context = self._build_context()
        goals = self._goals_in_order()
        today = date.today()
        current = (today.year, today.month)

        events: list[tuple[str, int, int, str, float]] = [
            (
                str(row.date)[:10],
                _ORDER["entry"],
                int(row.goal_id),
                "entry",
                float(row.amount),
            )
            for row in self.repo.get_entries().itertuples()
        ]
        has_income = {g.id for g in goals if g.contribution_category}
        for event_date, goal_id, link_type, amount in context["events"]:
            kind = "income" if link_type == LINK_CONTRIBUTION else "spent"
            if kind == "income":
                has_income.add(goal_id)
            events.append((event_date, _ORDER[kind], goal_id, kind, amount))
        events.sort()

        known = {g.id for g in goals}
        states = {g.id: GoalState() for g in goals}
        months_seen = [month_key(e[0]) for e in events]
        months_seen += [month_key(g.start_month) for g in goals]
        first = min((m for m in months_seen if m), default=current)

        ledger = Ledger(states=states)
        liquid = self._opening_liquid()
        # Liquid money before the first month the ledger reports on.
        for key, amount in context["liquid"].items():
            if key < first:
                liquid += amount

        position = 0
        for key in iter_months(first, max(first, current)):
            moves = {gid: GoalState() for gid in known}
            while position < len(events) and month_key(events[position][0]) <= key:
                _, _, goal_id, kind, amount = events[position]
                position += 1
                if goal_id not in known:
                    continue
                self._apply(
                    states[goal_id], moves[goal_id], kind, amount, goal_id in has_income
                )
            liquid += context["liquid"].get(key, 0.0)
            ledger.liquid[key] = liquid
            ledger.monthly[key] = {
                gid: GoalState(**vars(s)) for gid, s in states.items()
            }
            ledger.moves[key] = moves
        # Anything dated after the current month (a deposit typed for later).
        while position < len(events):
            _, _, goal_id, kind, amount = events[position]
            position += 1
            if goal_id in known:
                self._apply(
                    states[goal_id], GoalState(), kind, amount, goal_id in has_income
                )
        ledger.liquid_now = liquid + sum(
            amount for key, amount in context["liquid"].items() if key > current
        )
        return ledger

    @staticmethod
    def _apply(
        state: GoalState, move: GoalState, kind: str, amount: float, owns_income: bool
    ) -> None:
        """Apply one dated event to a goal's running state and its month's move."""
        if kind == "entry":
            state.added += amount
            move.added += amount
            delta = amount
        elif kind == "income":
            state.income += amount
            move.income += amount
            delta = amount
        else:
            # A goal without income of its own never goes below zero: what
            # it could not pay came out of free cash and stays spent. A
            # refund always comes back to the goal.
            if owns_income or amount < 0:
                paid = amount
            else:
                paid = min(amount, max(0.0, state.balance))
            state.spent += paid
            move.spent += paid
            delta = -paid
        state.balance += delta
        move.balance += delta
        if abs(state.balance) < ROUNDING_EPSILON:
            state.balance = 0.0

    def _state_of(self, goal: SavingsGoal) -> GoalState:
        """Return a goal's state today (zeroes for a goal with no history)."""
        return self._ledger().states.get(goal.id, GoalState())

    def _free_cash_now(self) -> float:
        """Return free cash now: bank and cash, less everything goals hold."""
        return self._ledger().free_cash()

    def _added_this_month(self, goal_id: int) -> float:
        """Return the net money put into a goal by hand this month."""
        today = date.today()
        moves = self._ledger().moves.get((today.year, today.month), {})
        state = moves.get(goal_id)
        return state.added if state else 0.0
