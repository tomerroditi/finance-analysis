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
    is_investment_goal,
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
    #: ``{(goal_id, year, month): amount}`` of linked contributions each goal
    #: actually kept — incoming money past a goal's target spills to the pool.
    contributed: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{(goal_id, year, month): amount}`` each goal actually paid for out of
    #: what it held — spending past that came out of free cash instead.
    spent: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{(goal_id, year, month): amount}`` of free cash a rule-funded goal
    #: took to pay a bill its own income had not yet covered.
    fronted: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{(goal_id, year, month): amount}`` of surplus and fronted cash a
    #: rule-funded goal handed back to free cash once its income arrived.
    released: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{goal_id: amount}`` of the cash a funded investment goal holds — its
    #: income and surplus — not yet spent on its transfers.
    to_invest: dict[int, float] = field(default_factory=dict)
    #: ``{(goal_id, year, month): amount}`` a funded investment goal moved from
    #: the cash it holds into investments (negative: withdrawn back).
    invested: dict[tuple[int, int, int], float] = field(default_factory=dict)
    #: ``{goal_id: total funded}`` after the whole timeline.
    funded: dict[int, float] = field(default_factory=dict)
    #: ``{goal_id: total utilized}`` after the whole timeline.
    utilized: dict[int, float] = field(default_factory=dict)
    #: ``{goal_id: "YYYY-MM"}`` for goals that auto-closed during the pass.
    closed_month: dict[int, str] = field(default_factory=dict)
    #: ``{(year, month): surplus}`` pool available before any goal took a share,
    #: including incoming contributions that spilled past their goal.
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
        self,
        from_month: str | None = None,
        dry_run: bool = False,
        order: list[int] | None = None,
    ) -> dict[str, Any]:
        """Recompute allocation history under the current priorities.

        Everything is computed first and written last, in one transaction:
        the new order (if any), the deletion of the restated range and the
        rows that replace it commit together. Committed one by one, a request
        running alongside could see the history deleted but not yet rewritten
        and refill it under the old order. Computing before opening the
        transaction keeps the write lock to the writes themselves, and keeps
        the simulation's own reads — some repositories read on a connection
        of their own — out of it.

        Parameters
        ----------
        from_month : str or None, optional
            Earliest month (``YYYY-MM``) to restate. ``None`` rebuilds the
            whole timeline.
        dry_run : bool, optional
            When ``True``, compute the diff but write nothing — this is what
            backs the preview the user confirms before committing.
        order : list[int] or None, optional
            A new waterfall order (goal ids, first funded first) to restate
            under and persist in the same transaction. ``None`` keeps the
            stored priorities.

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
        self._order_override = order
        try:
            plan = self._simulate(recompute_from=start or (1, 1))
            recomputed_ids = [
                g.id for g in self._goals_in_order() if g.status != GOAL_STATUS_CLOSED
            ]
        finally:
            self._order_override = None
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
            with self.repo.atomic():
                if order is not None:
                    self.repo.set_priorities(order)
                self.repo.delete_allocations(recomputed_ids, *(start or (1, 1)))
                self._persist(plan)
            self._last_plan = plan

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
        goal_by_id = {g.id: g for g in goals}
        # An investment goal holds cash it has not invested yet (``to_invest``)
        # and pays for its transfers out of it. What it has invested is in a
        # holding, not in the bank an overspend drained, so a deficit never
        # reaches it.
        invests = {g.id for g in goals if is_investment_goal(g)}
        # A cash goal with a "saved into" rule is filled by its own income
        # first. A bill that lands before the income is paid with free cash
        # the goal borrows (``bridge``); every shekel of income that arrives
        # first repays one borrowed shekel.
        rule_funded = {
            g.id for g in goals if g.id not in invests and g.contribution_category
        }
        bridge = dict.fromkeys(rule_funded, 0.0)
        to_invest = dict.fromkeys(invests, 0.0)
        moved = dict.fromkeys(invests, 0.0)
        # Every goal takes its place in the waterfall. One filled by income of
        # its own takes surplus for what the income has not filled (``fill``),
        # and once the income arrives it comes first — the surplus it makes
        # unnecessary goes back to free cash. A deficit can reclaim the
        # surplus an income or investment goal holds, never its income or
        # what it invested.
        fill = dict.fromkeys(set(bridge) | set(to_invest), 0.0)
        # Surplus only ever covers what a goal's own income never will: the
        # history is known up to today, so a goal whose income meets its
        # target takes no free cash at all, even in the months before that
        # income lands — bills in those months are fronted and repaid.
        own_income: dict[int, float] = {}
        for source in ("direct", "funding"):
            for per_goal in context[source].values():
                for goal_id, amount in per_goal.items():
                    if goal_id in fill:
                        own_income[goal_id] = own_income.get(goal_id, 0.0) + amount
        surplus_room = {
            g.id: max(0.0, float(g.target_amount or 0.0) - own_income.get(g.id, 0.0))
            for g in goals
            if g.id in fill and g.id in own_income
        }

        def needs(goal_id: int) -> float:
            """Return what a goal still needs to reach its target."""
            target = float(goal_by_id[goal_id].target_amount or 0.0)
            return target - funded[goal_id] + bridge.get(goal_id, 0.0)

        def add_row(goal_id: int, amount: float) -> None:
            """Add to a goal's computed ledger row for the month being walked."""
            cell = (goal_id, year, month)
            plan.computed[cell] = round(plan.computed.get(cell, 0.0) + amount, 2)

        def repay_bridge(goal_id: int, take: float) -> float:
            """Repay a goal's borrowed free cash out of surplus it just took.

            Surplus that reaches a goal still owing for a bill repays that
            debt first, exactly as its income would. Returns what went back
            to free cash.
            """
            if goal_id not in bridge:
                return 0.0
            repay = round(min(bridge[goal_id], take), 2)
            if repay <= 0:
                return 0.0
            bridge[goal_id] -= repay
            funded[goal_id] -= repay
            cell = (goal_id, year, month)
            plan.released[cell] = plan.released.get(cell, 0.0) + repay
            return repay

        def give_back_fill(goal_id: int, overflow: float) -> float:
            """Hand surplus an income goal no longer needs back to free cash."""
            cash = to_invest.get(goal_id, overflow)
            release = round(min(fill[goal_id], overflow, max(0.0, cash)), 2)
            if release <= 0:
                return 0.0
            add_row(goal_id, -release)
            fill[goal_id] -= release
            funded[goal_id] -= release
            if goal_id in to_invest:
                to_invest[goal_id] -= release
            return release

        # An opening balance is money the goal held when it started, so it
        # leaves the pool in that month. Taking every opening balance out when
        # the *earliest* goal started drained a pool that later history still
        # needed — the next deficit then clawed from goals that had done
        # nothing, and claiming the free cash before a goal moved the very
        # figure it had just claimed. A goal that starts in the future
        # earmarks its opening balance today.
        opening_month = {g.id: min(start_of[g.id], current) for g in goals}

        plan.surplus = dict(context["surplus"])
        has_rows = {goal_id for goal_id, _, _ in stored}

        for year, month in iter_months(first_month, current):
            key = (year, month)
            opening = sum(
                float(g.opening_balance or 0.0)
                for g in goals
                if opening_month[g.id] == key
            )
            # The goals can claim more than the pool holds, which is a
            # bookkeeping artefact rather than real debt — an opening balance
            # never takes the pool below zero (or below a hole it already had),
            # so the first deficit month does not raid goals over a phantom one.
            if opening:
                free_cash = max(min(free_cash, 0.0), free_cash - opening)
            month_start = free_cash
            # The open month is always restated (it is provisional), as is
            # everything inside an explicit rebuild range. Every other month is
            # history: existing rows stand, and only goals with no row yet may
            # draw on whatever the month left unallocated.
            recompute = (
                recompute_from is not None and key >= recompute_from
            ) or key == current

            # Contributions are derived from transactions rather than stored,
            # so they are always current. One paid out of the account claims
            # its share of the pool before the waterfall runs. One that came
            # in already earmarked (a gift) never was free cash: its goal
            # keeps what it still needs, and the rest spills into the month's
            # surplus like any other income.
            drawn = context["drawn"].get(key, {})
            outgoing_total = 0.0
            spill = 0.0
            for goal_id, amount in context["direct"].get(key, {}).items():
                if goal_id not in funded:
                    continue
                if frozen[goal_id]:
                    plan.contributed[(goal_id, year, month)] = amount
                    continue
                outgoing = drawn.get(goal_id, 0.0)
                goal = goal_by_id[goal_id]
                # Income first repays what the goal borrowed for earlier bills.
                if goal_id in bridge and amount > 0 and bridge[goal_id] > 0:
                    release = round(min(bridge[goal_id], amount), 2)
                    bridge[goal_id] -= release
                    funded[goal_id] -= release
                    free_cash += release
                    plan.released[(goal_id, year, month)] = release
                target = float(goal.target_amount or 0.0)
                # Surplus the goal holds makes way for its income, so it does
                # not count against what the income may still fill.
                need = max(
                    0.0, target - funded[goal_id] + fill.get(goal_id, 0.0) - outgoing
                )
                kept = round(min(amount - outgoing, need), 2)
                spill += amount - outgoing - kept
                outgoing_total += outgoing
                funded[goal_id] += outgoing + kept
                plan.contributed[(goal_id, year, month)] = outgoing + kept
                if goal_id in fill and (
                    recompute or stored.get((goal_id, year, month)) is None
                ):
                    free_cash += give_back_fill(
                        goal_id, funded[goal_id] - bridge.get(goal_id, 0.0) - target
                    )

            # A funded investment goal's income becomes cash it holds, ready
            # to invest, on the same terms.
            for goal_id, amount in context["funding"].get(key, {}).items():
                if goal_id not in to_invest or frozen[goal_id]:
                    continue
                target = float(goal_by_id[goal_id].target_amount or 0.0)
                need = max(0.0, target - funded[goal_id] + fill[goal_id])
                kept = round(min(amount, need), 2) if amount > 0 else amount
                spill += amount - kept
                funded[goal_id] += kept
                to_invest[goal_id] += kept
                cell = (goal_id, year, month)
                plan.contributed[cell] = plan.contributed.get(cell, 0.0) + kept
                if recompute or stored.get(cell) is None:
                    free_cash += give_back_fill(goal_id, funded[goal_id] - target)

            surplus = context["surplus"].get(key, 0.0) + spill
            if spill:
                plan.surplus[key] = surplus
            # The pool tracks real money, so it moves with the whole month —
            # a deficit pulls it down just as a surplus lifts it. A pool that
            # went negative is refilled before any goal takes a shekel: only
            # what is left of the surplus after that reaches the waterfall.
            # Every shekel a goal takes is debited below, so what the goals
            # leave behind needs no separate step: it is already in the pool.
            free_cash += surplus
            pool = max(0.0, min(surplus, free_cash))
            # A hole carried in from an earlier month is that month's
            # overspend, already settled — less whatever this month's surplus
            # repaid. Only a fall below that reaches the goals.
            floor = min(0.0, month_start + max(0.0, surplus))

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

            pool -= outgoing_total
            free_cash -= outgoing_total
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
                        if goal.id in fill:
                            fill[goal.id] += amount
                        if goal.id in to_invest:
                            to_invest[goal.id] += amount
                        if amount > 0:
                            free_cash += repay_bridge(goal.id, amount)
                pool = max(0.0, pool)

            for goal in goals:
                if pool <= 0:
                    break
                if frozen[goal.id] or key < start_of[goal.id]:
                    continue
                # In a history month, a goal that already has a row has had its
                # say — only newcomers may take what is still unallocated. A
                # goal with rows in other months is no newcomer: it had its
                # turn here too, and took nothing because a goal above it was
                # given the month's surplus and then gave it back to a deficit
                # (a net row hides that, and left the surplus looking unclaimed).
                if not recompute and (
                    stored.get((goal.id, year, month)) is not None
                    or goal.id in has_rows
                ):
                    continue
                # Free cash a goal borrowed for a bill is not progress, so it
                # does not shrink what the goal still needs.
                borrowed = bridge.get(goal.id, 0.0)
                need = float(goal.target_amount or 0.0) - funded[goal.id] + borrowed
                if goal.id in surplus_room:
                    need = min(need, surplus_room[goal.id] - fill[goal.id])
                if need <= 0:
                    continue
                take = min(need, pool)
                if goal.monthly_cap is not None:
                    take = min(take, float(goal.monthly_cap))
                take = round(max(0.0, take), 2)
                if take <= 0:
                    continue
                add_row(goal.id, take)
                funded[goal.id] += take
                pool -= take
                free_cash -= take
                free_cash += repay_bridge(goal.id, take)
                if goal.id in fill:
                    fill[goal.id] += take
                if goal.id in to_invest:
                    to_invest[goal.id] += take

            # Spending out of a goal lands after the month's funding and never
            # reduces its target. A goal can only pay with what it holds, so a
            # bill past that came out of free cash. A goal with income of its
            # own on the way fronts the gap from free cash and owes it back
            # (it joins the bridge its income repays); any other goal simply
            # leaves that part of the bill with free cash. Either way the pool
            # pays, and like any overspend it reaches the goals only once the
            # pool is empty. A refund always lands back in its goal.
            for goal_id, amount in context["utilized"].get(key, {}).items():
                if goal_id not in utilized:
                    continue
                available = funded[goal_id] - utilized[goal_id]
                gap = round(max(0.0, amount - max(0.0, available)), 2)
                if goal_id in bridge and gap > 0 and not frozen[goal_id]:
                    funded[goal_id] += gap
                    bridge[goal_id] += gap
                    plan.fronted[(goal_id, year, month)] = gap
                    covered = amount
                else:
                    covered = amount - gap
                utilized[goal_id] += covered
                if covered:
                    plan.spent[(goal_id, year, month)] = covered
                free_cash -= gap

            # A month that spent more than it earned has already pulled the
            # pool down. Only once the pool is empty does the overspend reach
            # the goals, taking from the least important first — the mirror
            # image of the funding waterfall.
            if free_cash < floor - ROUNDING_EPSILON:
                shortfall = floor - free_cash
                free_cash = floor
                for goal in reversed(goals):
                    if shortfall <= ROUNDING_EPSILON:
                        break
                    if frozen[goal.id] or key < start_of[goal.id]:
                        continue
                    # A history month's existing rows stand, exactly as they
                    # do for funding — only an explicit rebuild restates them.
                    if not recompute and stored.get((goal.id, year, month)) is not None:
                        continue
                    # Money already spent out of a goal is gone; only what it
                    # still holds can be handed back — and of an income goal,
                    # only the surplus, never its income.
                    holds = (
                        to_invest[goal.id]
                        if goal.id in to_invest
                        else funded[goal.id] - utilized[goal.id]
                    )
                    if goal.id in fill:
                        holds = min(holds, fill[goal.id])
                    give_back = round(min(holds, shortfall), 2)
                    if give_back <= 0:
                        continue
                    add_row(goal.id, -give_back)
                    funded[goal.id] -= give_back
                    shortfall -= give_back
                    if goal.id in fill:
                        fill[goal.id] -= give_back
                    if goal.id in to_invest:
                        to_invest[goal.id] -= give_back
                # What is left was paid with money no goal can give back — a
                # goal's own income, or money already invested — or with money
                # this model does not track (an overdraft, an untagged
                # account). Either way it was spent, so the pool shows it as
                # negative rather than hiding it at zero, and the next
                # surpluses refill it before any goal is funded.
                free_cash -= shortfall

            # Money moved into an investment goal left the spendable balance,
            # so it leaves the pool — but it is the goal being met, not
            # overspending. It runs after the clawback so it can never take
            # money back out of another goal: a transfer the pool cannot cover
            # takes it below zero. A withdrawal hands the money back.
            invested_now = context["invested"].get(key, {})
            if invested_now:
                from_free_cash = 0.0
                for group, amount in invested_now.items():
                    candidates = [goal_id for goal_id in group if goal_id in funded]
                    if not candidates:
                        continue
                    shares, moves, unclaimed = self._split_transfer(
                        candidates,
                        amount,
                        to_invest,
                        moved,
                        # A goal with income of its own is filled by that
                        # income; a deposit it holds no cash for is not its.
                        {g: 0.0 if g in surplus_room else needs(g) for g in candidates},
                    )
                    for goal_id, share in shares:
                        funded[goal_id] += share
                        cell = (goal_id, year, month)
                        plan.contributed[cell] = plan.contributed.get(cell, 0.0) + share
                    for goal_id, move in moves:
                        cell = (goal_id, year, month)
                        plan.invested[cell] = plan.invested.get(cell, 0.0) + move
                    # Money a goal held as cash was already off the pool; only
                    # a deposit no goal's cash paid for leaves it, and only a
                    # withdrawal no goal invested comes back.
                    from_free_cash += sum(share for _, share in shares) + unclaimed
                free_cash -= from_free_cash

            # Adding zero turns the -0.0 a fully drained pool rounds to into 0.0.
            plan.free_cash[key] = round(free_cash, 2) + 0.0

            for goal in goals:
                if frozen[goal.id] or goal.id in invests:
                    continue
                target = float(goal.target_amount or 0.0)
                total = funded[goal.id]
                achieved = target > 0 and total >= target - ROUNDING_EPSILON
                owes = bridge.get(goal.id, 0.0) > ROUNDING_EPSILON
                if achieved and not owes and (total - utilized[goal.id]) <= 0:
                    frozen[goal.id] = True
                    plan.closed_month[goal.id] = month_str(key)

        plan.funded = funded
        plan.utilized = utilized
        plan.to_invest = {g: round(cash, 2) for g, cash in to_invest.items()}
        return plan

    @staticmethod
    def _split_transfer(
        candidates: list[int],
        amount: float,
        to_invest: dict[int, float],
        moved: dict[int, float],
        need: dict[int, float],
    ) -> tuple[list[tuple[int, float]], list[tuple[int, float]], float]:
        """Split one month's net transfer among the investment goals it matches.

        An investment goal counts its money as progress the moment it holds
        it, so investing cash it holds only moves it: a deposit draws on the
        cash each goal holds, highest in the waterfall first. What no goal's
        cash covers is new money invested toward the highest goal still short
        of its target — its progress, paid from free cash — or, with every
        goal full, an ordinary transfer. A withdrawal goes back into the cash
        of the goals that invested, highest first, never past what each
        invested; the rest is no goal's.

        Parameters
        ----------
        candidates : list[int]
            The matching goals, highest in the waterfall first.
        amount : float
            Net invested this month: positive deposits, negative withdrawals.
        to_invest : dict[int, float]
            Cash each goal holds; drawn down (or refilled) in place.
        moved : dict[int, float]
            What each goal has invested so far; updated in place.
        need : dict[int, float]
            What each goal still needs to reach its target.

        Returns
        -------
        tuple
            ``[(goal_id, share), ...]`` of new progress paid from free cash,
            ``[(goal_id, move), ...]`` of everything each goal invested (or
            withdrew), and the part that is no goal's.
        """
        shares: list[tuple[int, float]] = []
        moves: list[tuple[int, float]] = []
        left = amount
        if left > 0:
            for goal_id in candidates:
                if left <= ROUNDING_EPSILON:
                    break
                paid = round(min(max(0.0, to_invest[goal_id]), left), 2)
                if paid > 0:
                    to_invest[goal_id] -= paid
                    moved[goal_id] += paid
                    moves.append((goal_id, paid))
                    left -= paid
            taker = next((g for g in candidates if need[g] > ROUNDING_EPSILON), None)
            if taker is not None and left > ROUNDING_EPSILON:
                shares.append((taker, left))
                moves.append((taker, left))
                moved[taker] += left
                left = 0.0
        else:
            for goal_id in candidates:
                if left >= -ROUNDING_EPSILON:
                    break
                back = round(min(-left, max(0.0, moved[goal_id])), 2)
                if back > 0:
                    to_invest[goal_id] += back
                    moved[goal_id] -= back
                    moves.append((goal_id, -back))
                    left += back
        return shares, moves, left if abs(left) > ROUNDING_EPSILON else 0.0

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
        with self.repo.atomic():
            for (goal_id, year, month), amount in plan.computed.items():
                current = existing.get((goal_id, year, month))
                if current is not None and same_amount(current, amount):
                    continue
                self.repo.upsert_allocation(
                    goal_id, year, month, amount, ALLOCATION_AUTO
                )
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
