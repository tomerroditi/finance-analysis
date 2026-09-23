"""The savings-goal allocation engine.

Provides ``AllocationPlan`` (one simulation pass's outcome) and
``AllocationEngineMixin``: the month-by-month surplus waterfall with its
deficit clawback, persistence of the resulting ledger, and the explicit
``rebuild`` that restates history. Mixed into ``SavingsGoalService`` (see
``core.py``).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.errors import ValidationException
from backend.models.savings_goal import (
    ALLOCATION_AUTO,
    GOAL_STATUS_CLOSED,
    SavingsGoal,
)
from backend.services.savings_goals.common import (
    ROUNDING_EPSILON,
    iter_months,
    month_key,
    month_str,
    same_amount,
)


@dataclass
class AllocationPlan:
    """Outcome of one simulation pass over the goal timeline."""

    #: ``{(goal_id, year, month): amount}`` for months the pass recomputed.
    computed: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{goal_id: total funded}`` after the whole timeline.
    funded: dict[int, float] = field(default_factory=dict)
    #: ``{goal_id: total utilized}`` after the whole timeline.
    utilized: dict[int, float] = field(default_factory=dict)
    #: ``{goal_id: "YYYY-MM"}`` for goals that auto-closed during the pass.
    closed_month: dict[int, str] = field(default_factory=dict)
    #: ``{(year, month): surplus}`` pool available before any goal took a share.
    surplus: dict[tuple[int, int], float] = field(default_factory=dict)
    #: ``{(year, month): free cash}`` left unearmarked at the end of each month.
    free_cash: dict[tuple[int, int], float] = field(default_factory=dict)


class AllocationEngineMixin:
    """Allocation simulation and ledger persistence for ``SavingsGoalService``."""

    def ensure_allocations(self) -> None:
        """Fill in any months the ledger is missing and refresh the open month.

        Closed months already on record are left exactly as they are — this is
        what keeps a later priority change from silently restating history.
        The current month is always recomputed, since it is provisional until
        the month ends.
        """
        plan = self._simulate(recompute_from=None)
        self._last_plan = plan
        self._persist(plan)

    def rebuild(
        self, from_month: str | None = None, dry_run: bool = False
    ) -> dict[str, Any]:
        """Recompute allocation history under the current priorities.

        Parameters
        ----------
        from_month : str or None, optional
            Earliest month (``YYYY-MM``) to restate. ``None`` rebuilds the
            whole timeline.
        dry_run : bool, optional
            When ``True``, compute the diff but write nothing — this is what
            backs the preview the user confirms before committing.

        Returns
        -------
        dict
            ``from_month``, ``dry_run``, and a ``changes`` list of per-goal
            before/after totals over the rebuilt range. Closed goals never
            appear: their allocations are frozen and money can't be taken back
            out of them. ``goals`` carries the refreshed goals (empty on a
            dry run).

        Raises
        ------
        ValidationException
            If ``from_month`` is not a parseable ``YYYY-MM`` string.
        """
        start = month_key(from_month) if from_month else None
        if from_month and start is None:
            raise ValidationException(f"Invalid from_month: {from_month!r}")

        before = self._range_totals(start)
        plan = self._simulate(recompute_from=start or (1, 1))
        after: dict[int, float] = {}
        for (goal_id, year, month), amount in plan.computed.items():
            if start is None or (year, month) >= start:
                after[goal_id] = after.get(goal_id, 0.0) + amount

        goal_names = {g.id: g.name for g in self._goals_in_order()}
        changes = []
        for goal_id in sorted(set(before) | set(after)):
            was, now = (
                round(before.get(goal_id, 0.0), 2),
                round(after.get(goal_id, 0.0), 2),
            )
            changes.append(
                {
                    "goal_id": goal_id,
                    "name": goal_names.get(goal_id, ""),
                    "before": was,
                    "after": now,
                    "delta": round(now - was, 2),
                }
            )

        if not dry_run:
            recomputed_ids = [
                g.id for g in self._goals_in_order() if g.status != GOAL_STATUS_CLOSED
            ]
            self.repo.delete_allocations(recomputed_ids, *(start or (1, 1)))
            self._persist(plan)

        return {
            "from_month": from_month,
            "dry_run": dry_run,
            "changes": changes,
            "goals": self._enriched_goals() if not dry_run else [],
        }

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _simulate(
        self,
        recompute_from: tuple[int, int] | None,
        goals: list[SavingsGoal] | None = None,
    ) -> AllocationPlan:
        """Walk the timeline month by month, allocating surplus to goals.

        Parameters
        ----------
        recompute_from : tuple or None
            When a ``(year, month)`` tuple, every month from there on is
            recomputed. When ``None``, only months with no ledger rows yet —
            plus the always-provisional current month — are computed, and
            everything else is replayed from what is already stored.
        goals : list or None, optional
            The goals to walk, in waterfall order. ``None`` walks every goal;
            a subset answers "what would the pool look like without this one"
            and must never be persisted.

        Returns
        -------
        AllocationPlan
            Computed allocations plus the funded/utilized/closed state each
            goal ends the timeline in.
        """
        if goals is None:
            goals = self._goals_in_order()
        plan = AllocationPlan()
        if not goals:
            return plan

        context = self._build_context()
        stored = self._stored_allocations()

        today = date.today()
        current = (today.year, today.month)
        starts = [month_key(g.start_month) or current for g in goals]
        first_month = min(starts)
        if first_month > current:
            return plan

        funded = {g.id: float(g.opening_balance or 0.0) for g in goals}
        utilized = {g.id: 0.0 for g in goals}
        # Investment backing is a present-tense fact about a holding, not a
        # dated event, so it is applied as it stands today. That means it only
        # steers months this pass computes — history already on record keeps
        # its rows, exactly as it does when a priority changes.
        backing = self._investment_backing()
        backed = {g.id: float(backing.get(g.id, 0.0)) for g in goals}
        # The pool opens at the spendable money the user had when the first
        # goal started: the capital that predates tracking, walked forward
        # through every month of realized cash flow before the walk begins.
        # Anchoring on prior wealth alone would ignore years of history the
        # goals never saw.
        #
        # That history floors at zero month by month, exactly as the walk
        # below does. Summing it and flooring once would put the floor at the
        # earliest goal's start month, so deleting that goal moved the floor,
        # changed how much the floor absorbed, and lost free cash with it.
        free_cash = self._pool_before(first_month, context)
        # A goal closed by the user is frozen from the outset; one that fills
        # and is fully spent closes partway through the walk.
        frozen = {g.id: g.status == GOAL_STATUS_CLOSED for g in goals}
        start_of = dict(zip((g.id for g in goals), starts, strict=True))
        # An opening balance is money the goal held when it started, so it
        # leaves the pool in that month. Taking every opening balance out when
        # the *earliest* goal started drained a pool that later history still
        # needed — the next deficit then clawed from goals that had done
        # nothing, and claiming the free cash before a goal moved the very
        # figure it had just claimed. A goal that starts in the future
        # earmarks its opening balance today.
        opening_month = {g.id: min(start_of[g.id], current) for g in goals}

        plan.surplus = context["surplus"]

        for year, month in iter_months(first_month, current):
            key = (year, month)
            opening = sum(
                float(g.opening_balance or 0.0)
                for g in goals
                if opening_month[g.id] == key
            )
            # The goals can claim more than the pool holds, which is a
            # bookkeeping artefact rather than real debt — floor it at zero so
            # the first deficit month does not raid goals over a phantom hole.
            if opening:
                free_cash = max(0.0, free_cash - opening)
            # The open month is always restated (it is provisional), as is
            # everything inside an explicit rebuild range. Every other month is
            # history: existing rows stand, and only goals with no row yet may
            # draw on whatever the month left unallocated.
            recompute = (
                recompute_from is not None and key >= recompute_from
            ) or key == current

            surplus = context["surplus"].get(key, 0.0)
            # The pool tracks real money, so it moves with the whole month —
            # a deficit pulls it down just as a surplus lifts it. Only the
            # positive part is ever handed to the waterfall, and every shekel
            # a goal takes is debited below, so what the goals leave behind
            # needs no separate step: it is already in the pool.
            free_cash += surplus
            pool = max(0.0, surplus)

            # A closed goal keeps whatever it was given; that money is spoken
            # for, so it leaves the pool before anyone else draws on it.
            for goal in goals:
                if frozen[goal.id]:
                    amount = stored.get((goal.id, year, month), 0.0)
                    if amount:
                        funded[goal.id] += amount
                        # Only funding drains the month's distributable pool.
                        # A replayed clawback is negative — it hands money
                        # back to the free-cash pool, not to the waterfall.
                        pool -= max(0.0, amount)
                        free_cash -= amount

            # Contributions are derived from transactions rather than stored,
            # so they are always current — and they claim their share of the
            # pool before the waterfall runs.
            for goal_id, amount in context["direct"].get(key, {}).items():
                if goal_id in funded and not frozen[goal_id]:
                    funded[goal_id] += amount
                    pool -= amount
                    free_cash -= amount
            pool = max(0.0, pool)

            if not recompute:
                for goal in goals:
                    if frozen[goal.id]:
                        continue
                    amount = stored.get((goal.id, year, month))
                    if amount is not None:
                        funded[goal.id] += amount
                        pool -= max(0.0, amount)
                        free_cash -= amount
                pool = max(0.0, pool)

            for goal in goals:
                if pool <= 0:
                    break
                if frozen[goal.id] or key < start_of[goal.id]:
                    continue
                # In a history month, a goal that already has a row has had its
                # say — only newcomers may take what is still unallocated.
                if not recompute and stored.get((goal.id, year, month)) is not None:
                    continue
                # An earmarked holding already covers part of the goal, so
                # only the uncovered remainder draws on the month's surplus.
                need = (
                    float(goal.target_amount or 0.0) - funded[goal.id] - backed[goal.id]
                )
                if need <= 0:
                    continue
                take = min(need, pool)
                if goal.monthly_cap is not None:
                    take = min(take, float(goal.monthly_cap))
                take = round(max(0.0, take), 2)
                if take <= 0:
                    continue
                plan.computed[(goal.id, year, month)] = take
                funded[goal.id] += take
                pool -= take
                free_cash -= take

            # A month that spent more than it earned has already pulled the
            # pool down. Only once the pool is empty does the overspend reach
            # the goals, taking from the least important first — the mirror
            # image of the funding waterfall.
            if free_cash < -ROUNDING_EPSILON:
                shortfall = -free_cash
                free_cash = 0.0
                for goal in reversed(goals):
                    if shortfall <= ROUNDING_EPSILON:
                        break
                    if frozen[goal.id] or key < start_of[goal.id]:
                        continue
                    # A history month's existing rows stand, exactly as they
                    # do for funding — only an explicit rebuild restates them.
                    if not recompute and stored.get((goal.id, year, month)) is not None:
                        continue
                    # Money already spent out of a goal is gone, and an
                    # earmarked holding is not cash — an overspend drains the
                    # bank, it cannot reach into the bond. Only the goal's
                    # unspent *cash* can be handed back.
                    give_back = round(
                        min(funded[goal.id] - utilized[goal.id], shortfall), 2
                    )
                    if give_back <= 0:
                        continue
                    plan.computed[(goal.id, year, month)] = -give_back
                    funded[goal.id] -= give_back
                    shortfall -= give_back
                # An overspend the goals cannot cover came out of money this
                # model does not track (an overdraft, an untagged account).
                # The pool is empty either way; it never goes negative.

            # Adding zero turns the -0.0 a fully drained pool rounds to into 0.0.
            plan.free_cash[key] = round(free_cash, 2) + 0.0

            # Money spent back out of a goal lands after that month's funding,
            # and never reduces the target — it is utilization, not a refund.
            for goal_id, amount in context["utilized"].get(key, {}).items():
                if goal_id in utilized:
                    utilized[goal_id] += amount

            for goal in goals:
                if frozen[goal.id]:
                    continue
                target = float(goal.target_amount or 0.0)
                total = funded[goal.id] + backed[goal.id]
                achieved = target > 0 and total >= target - ROUNDING_EPSILON
                if achieved and (total - utilized[goal.id]) <= 0:
                    frozen[goal.id] = True
                    plan.closed_month[goal.id] = month_str(key)

        plan.funded = funded
        plan.utilized = utilized
        return plan

    def _persist(self, plan: AllocationPlan) -> None:
        """Write a plan's computed allocations and any auto-closures.

        Rows the ledger already agrees with are skipped. ``ensure_allocations``
        runs from read paths and always recomputes the open month, so writing
        unconditionally meant every dashboard load committed several times over
        for numbers that had not moved — which churned the SQLite file, took a
        write lock per GET, and invalidated the cross-request caches
        (``backend/utils/data_cache.py``) mid-load, the one moment they are
        worth the most.
        """
        existing = self._stored_allocations()
        for (goal_id, year, month), amount in plan.computed.items():
            current = existing.get((goal_id, year, month))
            if current is not None and same_amount(current, amount):
                continue
            self.repo.upsert_allocation(goal_id, year, month, amount, ALLOCATION_AUTO)
        for goal_id, closed_month in plan.closed_month.items():
            goal = self.repo.get(goal_id)
            if goal and goal.status != GOAL_STATUS_CLOSED:
                self.repo.update(
                    goal_id, status=GOAL_STATUS_CLOSED, closed_month=closed_month
                )

    def _stored_allocations(self) -> dict[tuple[int, int, int], float]:
        """Return the persisted ledger as ``{(goal_id, year, month): amount}``."""
        df = self.repo.get_allocations()
        if df.empty:
            return {}
        return {
            (int(r.goal_id), int(r.year), int(r.month)): float(r.amount)
            for r in df.itertuples(index=False)
        }

    def _range_totals(self, start: tuple[int, int] | None) -> dict[int, float]:
        """Sum persisted allocations per goal at or after ``start``."""
        totals: dict[int, float] = {}
        for (goal_id, year, month), amount in self._stored_allocations().items():
            if start is None or (year, month) >= start:
                totals[goal_id] = totals.get(goal_id, 0.0) + amount
        return totals

    def _after_write(self) -> list[dict[str, Any]]:
        """Refresh the ledger after a mutation and return the enriched goals."""
        self.ensure_allocations()
        return self._enriched_goals()
