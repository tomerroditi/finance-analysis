"""Read models of the savings-goal service.

Provides ``ReadModelsMixin``: the goal list, free cash with its cover plan,
the month-by-month timeline and one month's movements for the budget view.
Mixed into ``SavingsGoalService`` (see ``core.py``).
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backend.models.savings_goal import GOAL_STATUS_CLOSED, SavingsGoal
from backend.services.savings_goals.common import ROUNDING_EPSILON, month_str

# Mean Gregorian month length, used to convert a day-accurate runway into
# months so `monthly_needed` reflects the time actually left.
DAYS_PER_MONTH = 30.44


def _money(value: float) -> float:
    """Round to agorot, without a negative zero."""
    return round(value, 2) + 0.0


@dataclass
class GoalPlan:
    """Where one goal stands against its target.

    Attributes
    ----------
    target : float
        The target amount (``0`` without one).
    remaining : float
        What is still to be saved.
    is_achieved : bool
        Whether the goal has saved its target.
    months_remaining : int or None
        Calendar months to the target date, ``None`` without one.
    monthly_needed : float or None
        What each month needs to reach the target by its date.
    is_past_due : bool
        Past its target date and still short.
    suggested : float
        What the card suggests putting in this month.
    """

    target: float
    remaining: float
    is_achieved: bool
    months_remaining: int | None = None
    monthly_needed: float | None = None
    is_past_due: bool = False
    suggested: float = 0.0


class ReadModelsMixin:
    """Goal payloads and read models for ``SavingsGoalService``."""

    def get_all(self) -> list[dict[str, Any]]:
        """Return every goal with what it holds and what it still needs.

        Returns
        -------
        list[dict]
            One payload per goal, in list order.
        """
        goals = self._goals_in_order()
        if not goals:
            return []
        entries = self.repo.get_entries()
        by_goal: dict[int, list[dict[str, Any]]] = {}
        for row in entries.iloc[::-1].itertuples():
            by_goal.setdefault(int(row.goal_id), []).append(
                {
                    "id": int(row.id),
                    "goal_id": int(row.goal_id),
                    "date": str(row.date)[:10],
                    "amount": _money(float(row.amount)),
                    "source": row.source,
                    "note": None if pd.isna(row.note) else row.note,
                }
            )
        return [self._enrich(goal, by_goal.get(goal.id, [])) for goal in goals]

    def get_free_cash(self) -> dict[str, Any]:
        """Return the bank and cash money no goal holds, and how to cover a shortfall.

        Returns
        -------
        dict
            ``free_cash`` (negative when goals hold more than there is),
            ``earmarked`` (what goals hold), ``liquid`` (bank and cash),
            ``has_goals``, ``shortfall`` and ``cover_plan`` (see
            :meth:`cover_plan`).
        """
        goals = self._goals_in_order()
        if not goals:
            return {
                "free_cash": 0.0,
                "earmarked": 0.0,
                "liquid": 0.0,
                "has_goals": False,
                "shortfall": 0.0,
                "cover_plan": [],
            }
        ledger = self._ledger()
        free_cash = ledger.free_cash()
        return {
            "free_cash": _money(free_cash),
            "earmarked": _money(sum(s.available for s in ledger.states.values())),
            "liquid": _money(ledger.liquid_now),
            "has_goals": True,
            "shortfall": _money(max(0.0, -free_cash)),
            "cover_plan": self.cover_plan(),
        }

    def get_timeline(self, months: int | None = 12) -> dict[str, Any]:
        """Return each goal's balance month by month, with free cash beside it.

        Parameters
        ----------
        months : int or None, optional
            How many months, ending with the current one; ``0`` or ``None``
            returns every month since the first thing a goal recorded.

        Returns
        -------
        dict
            ``has_goals``, ``total_months`` (how many months there are in
            all), ``months`` (oldest first: ``month``, ``free_cash`` and per
            goal ``balance`` — what it held at the month's end — and
            ``change``) and ``goals`` (id, name, priority, status).
        """
        goals = self._goals_in_order()
        if not goals:
            return {"has_goals": False, "total_months": 0, "months": [], "goals": []}
        ledger = self._ledger()
        keys = sorted(ledger.monthly)
        total_months = len(keys)
        if months:
            keys = keys[-months:]
        rows = [
            {
                "month": month_str(key),
                "free_cash": _money(ledger.free_cash(key)),
                "goals": [
                    {
                        "goal_id": goal.id,
                        "balance": _money(ledger.monthly[key][goal.id].available),
                        "change": _money(
                            ledger.monthly[key][goal.id].available
                            - self._held_before(ledger, key, goal.id)
                        ),
                    }
                    for goal in goals
                ],
            }
            for key in keys
        ]
        return {
            "has_goals": True,
            "total_months": total_months,
            "months": rows,
            "goals": [
                {
                    "id": goal.id,
                    "name": goal.name,
                    "priority": goal.priority,
                    "status": goal.status,
                    "is_closed": goal.status == GOAL_STATUS_CLOSED,
                }
                for goal in goals
            ],
        }

    def get_month(self, year: int, month: int) -> dict[str, Any]:
        """Return what moved into and out of each goal in one month.

        Parameters
        ----------
        year, month : int
            The calendar month.

        Returns
        -------
        dict
            ``year``, ``month``, ``goals`` (only goals with any movement:
            ``added``, ``income``, ``spent`` and ``change``), ``total_added``
            and ``total_change``.
        """
        payload: dict[str, Any] = {
            "year": year,
            "month": month,
            "goals": [],
            "total_added": 0.0,
            "total_change": 0.0,
        }
        goals = self._goals_in_order()
        if not goals:
            return payload
        moves = self._ledger().moves.get((year, month), {})
        rows = []
        for goal in goals:
            move = moves.get(goal.id)
            if move is None or all(
                abs(v) < ROUNDING_EPSILON for v in (move.added, move.income, move.spent)
            ):
                continue
            rows.append(
                {
                    "goal_id": goal.id,
                    "name": goal.name,
                    "priority": goal.priority,
                    "status": goal.status,
                    "added": _money(move.added),
                    "income": _money(move.income),
                    "spent": _money(move.spent),
                    "change": _money(move.added + move.income - move.spent),
                }
            )
        payload["goals"] = rows
        payload["total_added"] = _money(sum(r["added"] for r in rows))
        payload["total_change"] = _money(sum(r["change"] for r in rows))
        return payload

    @staticmethod
    def _held_before(ledger: Any, key: tuple[int, int], goal_id: int) -> float:
        """Return what a goal held at the end of the month before ``key``."""
        earlier = [k for k in ledger.monthly if k < key]
        if not earlier:
            return 0.0
        return ledger.monthly[max(earlier)][goal_id].available

    def cover_plan(self) -> list[dict[str, Any]]:
        """Return what covering a free-cash shortfall would take from each goal.

        Lowest in the list gives first, and no goal gives more than it holds.

        Returns
        -------
        list[dict]
            ``{"goal_id", "name", "amount"}`` per goal giving money back;
            empty when free cash is not negative.
        """
        shortfall = -self._free_cash_now()
        plan: list[dict[str, Any]] = []
        for goal in reversed(self._goals_in_order()):
            if shortfall <= ROUNDING_EPSILON:
                break
            if goal.status == GOAL_STATUS_CLOSED:
                continue
            take = min(shortfall, self._state_of(goal).available)
            if take <= ROUNDING_EPSILON:
                continue
            plan.append(
                {"goal_id": goal.id, "name": goal.name, "amount": round(take, 2)}
            )
            shortfall -= take
        return plan

    def _plan_for(self, goal: SavingsGoal) -> "GoalPlan":
        """Return where a goal stands against its target, and this month's ask."""
        state = self._state_of(goal)
        target = float(goal.target_amount or 0.0)
        remaining = max(0.0, target - state.saved)
        achieved = target > 0 and state.saved >= target - ROUNDING_EPSILON
        added_now = self._added_this_month(goal.id)
        plan = GoalPlan(target=target, remaining=remaining, is_achieved=achieved)

        runway = 0.0
        if goal.target_date and pd.notna(goal.target_date):
            today = pd.Timestamp.today().normalize()
            target_ts = pd.Timestamp(goal.target_date)
            months = (target_ts.year - today.year) * 12 + (
                target_ts.month - today.month
            )
            plan.months_remaining = max(0, int(months))
            plan.is_past_due = not achieved and target_ts < today
            # Size it off the real runway in days: a calendar-month difference
            # treats a goal due on the 1st two months out as two full months
            # even when only ~39 days remain.
            runway = max(0, (target_ts - today).days) / DAYS_PER_MONTH
            if not achieved:
                plan.monthly_needed = _money(
                    remaining / runway if runway > 0 else remaining
                )

        if goal.status == GOAL_STATUS_CLOSED or achieved:
            return plan
        if goal.monthly_amount:
            base = float(goal.monthly_amount)
        elif runway > 0:
            # What the month needed before anything went in this month, so
            # funding it does not shrink the suggestion twice.
            base = (remaining + max(0.0, added_now)) / runway
        else:
            base = 0.0
        plan.suggested = _money(min(max(0.0, base - added_now), remaining))
        return plan

    def _enrich(
        self, goal: SavingsGoal, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Assemble one goal's payload."""
        state = self._state_of(goal)
        plan = self._plan_for(goal)
        return {
            "id": goal.id,
            "name": goal.name,
            "target_amount": _money(plan.target),
            "priority": goal.priority,
            "monthly_amount": goal.monthly_amount,
            "start_month": goal.start_month,
            "target_date": goal.target_date,
            "contribution_category": goal.contribution_category,
            "contribution_tags": goal.contribution_tags,
            "utilization_category": goal.utilization_category,
            "utilization_tags": goal.utilization_tags,
            "status": goal.status,
            "closed_month": goal.closed_month,
            "notes": goal.notes,
            "added": _money(state.added),
            "income": _money(state.income),
            "spent": _money(state.spent),
            "saved": _money(state.saved),
            "balance": _money(state.balance),
            "available": _money(state.available),
            "owed": _money(state.owed),
            "remaining": _money(plan.remaining),
            "progress_pct": round(
                min(
                    100.0, (state.saved / plan.target * 100) if plan.target > 0 else 0.0
                ),
                1,
            ),
            "is_achieved": plan.is_achieved,
            "is_closed": goal.status == GOAL_STATUS_CLOSED,
            "months_remaining": plan.months_remaining,
            "monthly_needed": plan.monthly_needed,
            "is_past_due": plan.is_past_due,
            "added_this_month": _money(self._added_this_month(goal.id)),
            "suggested_this_month": plan.suggested,
            "entries": entries,
        }
