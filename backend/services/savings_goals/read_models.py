"""Read models of the savings-goal service.

Provides ``ReadModelsMixin``: the enriched goal list, one month's allocations
for the budget view, the free-cash pool (now and before a given month) and the
month-by-month timeline. Mixed into ``SavingsGoalService`` (see ``core.py``).
"""

from datetime import date
from typing import Any

import pandas as pd

from backend.errors import ValidationException
from backend.models.savings_goal import (
    GOAL_KIND_CASH,
    GOAL_STATUS_CLOSED,
    SavingsGoal,
)
from backend.services.savings_goals.common import (
    ROUNDING_EPSILON,
    is_investment_goal,
    iter_months,
    month_key,
    month_str,
)

# Mean Gregorian month length, used to convert a day-accurate runway into
# months so `monthly_needed` reflects the time actually left.
DAYS_PER_MONTH = 30.44


class ReadModelsMixin:
    """Goal payloads and ledger read models for ``SavingsGoalService``."""

    def get_all(self) -> list[dict[str, Any]]:
        """Return all goals enriched with progress metrics, in waterfall order.

        Running this refreshes the allocation ledger first, so the numbers a
        caller sees always include the provisional current month.

        Returns
        -------
        list[dict]
            Goal dicts ordered by priority ascending.
        """
        self.ensure_allocations()
        return self._enriched_goals()

    def get_month_allocations(self, year: int, month: int) -> dict[str, Any]:
        """Return what each goal received in one month, for the budget view.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).

        Returns
        -------
        dict
            ``goals`` (per-goal allocation rows), ``total_allocated``,
            ``surplus`` for the month, ``unallocated`` remainder,
            ``free_cash`` left in the pool at month end, ``clawed_back``
            (money a deficit pulled back out of goals, positive), and
            ``is_provisional`` — true while the month is still open, because
            the figures move as new transactions land.
        """
        today = date.today()
        is_provisional = (year, month) >= (today.year, today.month)
        empty_month = {
            "year": year,
            "month": month,
            "goals": [],
            "total_allocated": 0.0,
            "surplus": 0.0,
            "unallocated": 0.0,
            "free_cash": 0.0,
            "clawed_back": 0.0,
            "is_provisional": is_provisional,
        }
        # Short-circuit before touching transactions. The budget page renders
        # this section on every month it shows, so for the many users who keep
        # no goals it has to cost nothing.
        if not self._goals_in_order():
            return empty_month

        self.ensure_allocations()
        allocations = self.repo.get_month_allocations(year, month)
        by_goal = (
            dict(zip(allocations["goal_id"], allocations["amount"], strict=True))
            if not allocations.empty
            else {}
        )

        direct = self._kept_contributions().get((year, month), {})
        moves = self._bridge_moves().get((year, month), {})
        surplus = self._last_plan.surplus.get((year, month), 0.0)

        rows = []
        for goal in self._goals_in_order():
            allocated = float(by_goal.get(goal.id, 0.0))
            contributed = float(direct.get(goal.id, 0.0))
            bridged = float(moves.get(goal.id, 0.0))
            if allocated == 0 and contributed == 0 and bridged == 0:
                continue
            rows.append(
                {
                    "goal_id": goal.id,
                    "name": goal.name,
                    "priority": goal.priority,
                    "status": goal.status,
                    "allocated": round(allocated, 2),
                    "contributed": round(contributed, 2),
                    "bridged": round(bridged, 2),
                    "total": round(allocated + contributed + bridged, 2),
                }
            )

        total = sum(row["total"] for row in rows)
        plan = self._last_plan
        clawed = -sum(amount for amount in by_goal.values() if amount < 0)
        return {
            "year": year,
            "month": month,
            "goals": rows,
            "total_allocated": round(total, 2),
            "surplus": round(surplus, 2),
            "unallocated": round(max(0.0, surplus - total), 2),
            "free_cash": round(float(plan.free_cash.get((year, month), 0.0)), 2)
            if plan
            else 0.0,
            "clawed_back": round(clawed, 2),
            "is_provisional": is_provisional,
        }

    def get_free_cash(self) -> dict[str, float | bool]:
        """Return the pool of tracked money that no goal has earmarked.

        The pool is the counterweight to the goals: liquid money (bank + cash)
        minus what every goal still holds. It is what a deficit month drains
        before any goal is touched.

        Returns
        -------
        dict
            ``free_cash`` (the unearmarked pool), ``earmarked`` (the *cash*
            every cash goal still holds), ``liquid`` (the two together),
            ``clawed_back_this_month`` and
            ``has_goals``. With no goals the figures are zero and no
            transaction scan happens — the pool only means something relative
            to goals.
        """
        empty = {
            "free_cash": 0.0,
            "earmarked": 0.0,
            "liquid": 0.0,
            "clawed_back_this_month": 0.0,
            "has_goals": False,
        }
        if not self._goals_in_order():
            return empty

        goals = self.get_all()
        plan = self._last_plan
        today = date.today()
        current = (today.year, today.month)
        free_cash = float(plan.free_cash.get(current, 0.0)) if plan else 0.0
        # An investment goal's progress sits in the holding it was moved
        # into, never in this pool's accounts.
        earmarked = sum(
            max(0.0, g["available"]) for g in goals if g["kind"] == GOAL_KIND_CASH
        )
        this_month = self.repo.get_month_allocations(*current)
        clawed = (
            -float(this_month.loc[this_month["amount"] < 0, "amount"].sum())
            if not this_month.empty
            else 0.0
        )
        return {
            "free_cash": round(free_cash, 2),
            "earmarked": round(earmarked, 2),
            "liquid": round(free_cash + earmarked, 2),
            "clawed_back_this_month": round(clawed, 2),
            "has_goals": True,
        }

    def get_free_cash_before(
        self, month: str, goal_id: int | None = None
    ) -> dict[str, str | float]:
        """Return the free cash a goal starting in ``month`` could take over.

        Goals only ever draw on each month's *new* surplus, so money that was
        already in the accounts when a goal started stays in the free-cash
        pool for good. Setting a goal's opening balance to this figure is how
        the user earmarks that money for it.

        The goal itself is left out of the walk, so the answer does not
        depend on the opening balance or the allocations it already has.

        Parameters
        ----------
        month : str
            The goal's start month, ``YYYY-MM``.
        goal_id : int or None, optional
            The goal being edited. ``None`` for a goal not created yet.

        Returns
        -------
        dict
            ``month`` (echoed) and ``free_cash`` — the pool at the start of
            that month, never negative.

        Raises
        ------
        ValidationException
            If ``month`` is not a parseable ``YYYY-MM`` string.
        """
        key = month_key(month)
        if key is None:
            raise ValidationException(f"Invalid month: {month!r}")

        today = date.today()
        current = (today.year, today.month)
        others = [g for g in self._goals_in_order() if g.id != goal_id]
        context = self._build_context()
        starts = [month_key(g.start_month) or current for g in others]

        if not others or key <= min(starts):
            amount = self._pool_before(key, context)
        elif key > current:
            # A future start sees today's pool, which the walk has already
            # debited for every opening balance due by now.
            plan = self._simulate(recompute_from=None, goals=others)
            return {
                "month": month_str(key),
                "free_cash": round(float(plan.free_cash.get(current, 0.0)), 2) + 0.0,
            }
        else:
            year, mon = key
            previous = (year, mon - 1) if mon > 1 else (year - 1, 12)
            plan = self._simulate(recompute_from=None, goals=others)
            amount = float(plan.free_cash.get(previous, 0.0))
        # Another goal starting the same month takes its opening balance out
        # of the same money first, exactly as the walk does.
        same_month = sum(
            float(g.opening_balance or 0.0)
            for g, start in zip(others, starts, strict=True)
            if min(start, current) == min(key, current)
        )
        amount = max(0.0, amount - same_month)

        return {"month": month_str(key), "free_cash": round(amount, 2) + 0.0}

    def get_timeline(self, months: int | None = 12) -> dict[str, Any]:
        """Return the month-by-month history of the waterfall.

        The dashboard card shows a goal's *current* standing; this is the same
        ledger read the other way round — one row per month, with what each
        goal took, what a deficit took back, and what was left over in the
        free-cash pool. Reading it per month is the only way to see that a
        goal stalled in March or that the pool has been empty since spring.

        Parameters
        ----------
        months : int or None, optional
            How many trailing months to return, ending with the current one.
            ``None`` returns the whole history. ``total_months`` always
            reports the full length, so a caller can offer "all time" only
            when there is more to show.

        Returns
        -------
        dict
            ``months`` (oldest first), ``goals`` (waterfall order, for stable
            series colours), ``total_months`` and ``has_goals``. Every month
            between the first and the current one is present, including the
            ones where nothing moved — a gap in a time series reads as zero,
            not as "skipped".
        """
        today = date.today()
        current = (today.year, today.month)
        goals = self._goals_in_order()
        if not goals:
            return {"has_goals": False, "total_months": 0, "months": [], "goals": []}

        self.ensure_allocations()
        plan = self._last_plan
        kept = self._kept_contributions()
        bridge_moves = self._bridge_moves()

        ledger: dict[tuple[int, int], dict[int, float]] = {}
        for (goal_id, year, month), amount in self._stored_allocations().items():
            ledger.setdefault((year, month), {})[goal_id] = amount

        starts = [month_key(g.start_month) or current for g in goals]
        first = min([*starts, *ledger.keys(), current])

        rows = []
        for key in iter_months(first, current):
            per_goal = ledger.get(key, {})
            direct = kept.get(key, {})
            moves = bridge_moves.get(key, {})
            goal_rows = []
            for goal in goals:
                allocated = float(per_goal.get(goal.id, 0.0))
                contributed = float(direct.get(goal.id, 0.0))
                bridged = float(moves.get(goal.id, 0.0))
                if allocated == 0 and contributed == 0 and bridged == 0:
                    continue
                goal_rows.append(
                    {
                        "goal_id": goal.id,
                        "name": goal.name,
                        "allocated": round(allocated, 2),
                        "contributed": round(contributed, 2),
                        "bridged": round(bridged, 2),
                        "total": round(allocated + contributed + bridged, 2),
                    }
                )
            # Funding and clawback are reported apart rather than netted: a
            # month that gave a goal 3,000 and took 800 back out of another
            # did both, and a single net figure would hide half of it.
            funded = sum(row["total"] for row in goal_rows if row["total"] > 0)
            clawed = -sum(amount for amount in per_goal.values() if amount < 0)
            rows.append(
                {
                    "month": month_str(key),
                    "goals": goal_rows,
                    "allocated": round(funded, 2),
                    "clawed_back": round(clawed, 2),
                    "surplus": round(float(plan.surplus.get(key, 0.0)), 2)
                    if plan
                    else 0.0,
                    # Months the walk never reached (a stray ledger row that
                    # predates every goal's start) have no pool figure; zero
                    # is the honest reading — nothing was earmarked yet.
                    "free_cash": round(float(plan.free_cash.get(key, 0.0)), 2)
                    if plan
                    else 0.0,
                    "is_provisional": key >= current,
                }
            )

        total_months = len(rows)
        if months is not None and months > 0:
            rows = rows[-months:]

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

    def _enriched_goals(self) -> list[dict[str, Any]]:
        """Build the API payload for every goal from the current ledger."""
        goals = self._goals_in_order()
        if not goals:
            return []

        allocations = self.repo.get_allocations()
        totals: dict[int, float] = {}
        reclaimed: dict[int, float] = {}
        history: dict[int, list[dict[str, Any]]] = {}
        if not allocations.empty:
            for row in allocations.sort_values(["year", "month"]).itertuples(
                index=False
            ):
                goal_id = int(row.goal_id)
                amount = float(row.amount)
                totals[goal_id] = totals.get(goal_id, 0.0) + amount
                # A negative row is a deficit month taking money back out of
                # the goal; `allocated` nets it off, but the user still wants
                # to see how much was reclaimed.
                if amount < 0:
                    reclaimed[goal_id] = reclaimed.get(goal_id, 0.0) - amount
                history.setdefault(goal_id, []).append(
                    {
                        "month": month_str((int(row.year), int(row.month))),
                        "amount": round(amount, 2),
                    }
                )

        contributed: dict[int, float] = {}
        utilized: dict[int, float] = {}
        fronted: dict[int, float] = {}
        released: dict[int, float] = {}
        for bucket, sink in (
            (self._kept_contributions(), contributed),
            (self._goal_spending(), utilized),
            (self._per_month(self._last_plan.fronted), fronted),
            (self._per_month(self._last_plan.released), released),
        ):
            for per_goal in bucket.values():
                for goal_id, amount in per_goal.items():
                    sink[goal_id] = sink.get(goal_id, 0.0) + amount

        today = date.today()
        current = (today.year, today.month)
        provisional = {
            goal_id: next(
                (
                    entry["amount"]
                    for entry in rows
                    if entry["month"] == month_str(current)
                ),
                0.0,
            )
            for goal_id, rows in history.items()
        }
        # An investment goal has no ledger rows; what it gained this month is
        # the month's net transfers.
        this_month = self._kept_contributions().get(current, {})
        for goal in goals:
            if is_investment_goal(goal):
                provisional[goal.id] = this_month.get(goal.id, 0.0)

        return [
            self._enrich(
                goal,
                totals,
                contributed,
                utilized,
                history,
                provisional,
                reclaimed,
                fronted,
                released,
            )
            for goal in goals
        ]

    def _goal_spending(self) -> dict[tuple[int, int], dict[int, float]]:
        """Return what each goal paid for, as ``{(year, month): {goal_id: amount}}``.

        A goal pays only with what it holds, so this is the simulation's
        figure, not the raw linked spending: the part a goal could not cover
        came out of free cash.
        """
        if self._last_plan is None:
            self.ensure_allocations()
        return self._per_month(self._last_plan.spent)

    def _bridge_moves(self) -> dict[tuple[int, int], dict[int, float]]:
        """Return each month's fronted-minus-released cash per rule-funded goal.

        Free cash a goal fronted for a bill raises what it holds; surplus it
        hands back once its own income lands lowers it. Neither is a ledger
        row, so every view that nets a goal's month adds this in.
        """
        if self._last_plan is None:
            self.ensure_allocations()
        moves: dict[tuple[int, int], dict[int, float]] = {}
        for source, sign in (
            (self._last_plan.fronted, 1),
            (self._last_plan.released, -1),
        ):
            for (goal_id, year, month), amount in source.items():
                per_goal = moves.setdefault((year, month), {})
                per_goal[goal_id] = per_goal.get(goal_id, 0.0) + sign * amount
        return moves

    @staticmethod
    def _per_month(
        amounts: dict[tuple[int, int, int], float],
    ) -> dict[tuple[int, int], dict[int, float]]:
        """Regroup ``{(goal_id, year, month): amount}`` by month."""
        grouped: dict[tuple[int, int], dict[int, float]] = {}
        for (goal_id, year, month), amount in amounts.items():
            grouped.setdefault((year, month), {})[goal_id] = amount
        return grouped

    def _kept_contributions(self) -> dict[tuple[int, int], dict[int, float]]:
        """Return the contributions each goal kept, as ``{(year, month): {goal_id: amount}}``.

        Incoming money past a goal's target spills back into the month's
        surplus, so what a goal kept depends on how full it was at the time —
        only the simulation knows that, which is why this reads the last plan
        rather than the raw linked transactions.
        """
        if self._last_plan is None:
            self.ensure_allocations()
        kept: dict[tuple[int, int], dict[int, float]] = {}
        for (goal_id, year, month), amount in self._last_plan.contributed.items():
            kept.setdefault((year, month), {})[goal_id] = amount
        return kept

    @staticmethod
    def _enrich(
        goal: SavingsGoal,
        totals: dict[int, float],
        contributed: dict[int, float],
        utilized: dict[int, float],
        history: dict[int, list[dict[str, Any]]],
        provisional: dict[int, float],
        reclaimed: dict[int, float],
        fronted: dict[int, float],
        released: dict[int, float],
    ) -> dict[str, Any]:
        """Assemble one goal's derived progress metrics."""
        target = float(goal.target_amount or 0.0)
        opening = float(goal.opening_balance or 0.0)
        allocated = float(totals.get(goal.id, 0.0))
        contributions = float(contributed.get(goal.id, 0.0))
        spent = float(utilized.get(goal.id, 0.0))

        lent = float(fronted.get(goal.id, 0.0))
        repaid = float(released.get(goal.id, 0.0))
        # Free cash a rule-funded goal fronted is money it held for a while;
        # what its own income later released went back to free cash.
        funded = opening + allocated + contributions + lent - repaid
        available = funded - spent
        remaining = max(0.0, target - funded)
        progress_pct = round(
            min(100.0, (funded / target * 100) if target > 0 else 0.0), 1
        )
        is_achieved = target > 0 and funded >= target - ROUNDING_EPSILON

        months_remaining = None
        monthly_needed = None
        if goal.target_date and pd.notna(goal.target_date):
            today = pd.Timestamp.today().normalize()
            target_ts = pd.Timestamp(goal.target_date)
            months = (target_ts.year - today.year) * 12 + (
                target_ts.month - today.month
            )
            months_remaining = max(0, int(months))
            if not is_achieved:
                # Size the contribution off the real runway in days. A pure
                # calendar-month difference treats a goal due on the 1st two
                # months out as two full months even when only ~39 days
                # remain, understating what the user must save each month.
                days_remaining = max(0, (target_ts - today).days)
                months_of_runway = days_remaining / DAYS_PER_MONTH
                monthly_needed = (
                    round(remaining / months_of_runway, 2)
                    if months_of_runway > 0
                    else round(remaining, 2)
                )

        return {
            "id": goal.id,
            "name": goal.name,
            "target_amount": round(target, 2),
            "opening_balance": round(opening, 2),
            "priority": goal.priority,
            "monthly_cap": goal.monthly_cap,
            "start_month": goal.start_month,
            "target_date": goal.target_date,
            "contribution_category": goal.contribution_category,
            "contribution_tags": goal.contribution_tags,
            "utilization_category": goal.utilization_category,
            "utilization_tags": goal.utilization_tags,
            "kind": goal.kind or GOAL_KIND_CASH,
            "status": goal.status,
            "closed_month": goal.closed_month,
            "notes": goal.notes,
            "allocated": round(allocated, 2),
            "contributed": round(contributions, 2),
            "utilized": round(spent, 2),
            "fronted": round(lent, 2),
            "released": round(repaid, 2),
            "clawed_back": round(float(reclaimed.get(goal.id, 0.0)), 2),
            "funded": round(funded, 2),
            "available": round(available, 2),
            "remaining": round(remaining, 2),
            "progress_pct": progress_pct,
            "is_achieved": is_achieved,
            "is_closed": goal.status == GOAL_STATUS_CLOSED,
            "this_month_allocation": round(float(provisional.get(goal.id, 0.0)), 2),
            "months_remaining": months_remaining,
            "monthly_needed": monthly_needed,
            "history": history.get(goal.id, []),
        }
