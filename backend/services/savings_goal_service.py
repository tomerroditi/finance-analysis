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

Results are persisted per (goal, month) in ``savings_goal_allocations``. Past
months are never silently restated: a priority change applies going forward,
and rewriting history is an explicit ``rebuild`` the user previews first. Goals
that have been closed are frozen — their allocations are replayed as-is and can
never be pulled back out, even by a rebuild.
"""

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import PRIOR_WEALTH_TAG
from backend.constants.tables import TransactionsTableFields
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    ALLOCATION_AUTO,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
)
from backend.repositories.savings_goal_repository import SavingsGoalRepository
from backend.services.transaction_classification import transactions_masks
from backend.services.transactions_service import TransactionsService

# Mean Gregorian month length, used to convert a day-accurate runway into
# months so `monthly_needed` reflects the time actually left.
DAYS_PER_MONTH = 30.44

# Rows synthesised from prior-wealth balances are opening capital, not income.
# Counting them would hand one month an enormous phantom surplus.
_PRIOR_WEALTH_SOURCES = {"bank_balances", "investments"}

# Itemized credit-card rows duplicate the bank-side bill payment, and insurance
# rows are not cash flow. Same exclusion the cashflow analysis applies.
_SURPLUS_EXCLUDED_SOURCES = {"credit_card_transactions", "insurance_transactions"}

_ALL_TAGS = "all_tags"


def _month_key(value) -> tuple[int, int] | None:
    """Parse ``YYYY-MM`` (or ``YYYY-MM-DD``) into a ``(year, month)`` tuple."""
    if not value or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        ts = pd.Timestamp(str(value)[:7] + "-01")
    except (ValueError, TypeError):
        return None
    return int(ts.year), int(ts.month)


def _month_str(key: tuple[int, int]) -> str:
    """Render a ``(year, month)`` tuple as ``YYYY-MM``."""
    return f"{key[0]:04d}-{key[1]:02d}"


def _iter_months(start: tuple[int, int], end: tuple[int, int]):
    """Yield every ``(year, month)`` from ``start`` through ``end`` inclusive."""
    year, month = start
    while (year, month) <= end:
        yield year, month
        month += 1
        if month > 12:
            year, month = year + 1, 1


@dataclass
class _Plan:
    """Outcome of one simulation pass over the goal timeline."""

    #: ``{(goal_id, year, month): amount}`` for months the pass recomputed.
    computed: dict = field(default_factory=dict)
    #: ``{goal_id: total funded}`` after the whole timeline.
    funded: dict = field(default_factory=dict)
    #: ``{goal_id: total utilized}`` after the whole timeline.
    utilized: dict = field(default_factory=dict)
    #: ``{goal_id: "YYYY-MM"}`` for goals that auto-closed during the pass.
    closed_month: dict = field(default_factory=dict)
    #: ``{(year, month): surplus}`` pool available before any goal took a share.
    surplus: dict = field(default_factory=dict)


class SavingsGoalService:
    """Service for managing savings goals and distributing monthly surplus."""

    def __init__(self, db: Session):
        """Initialize the service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = SavingsGoalRepository(db)
        self.transactions_service = TransactionsService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
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

    def get_month_allocations(self, year: int, month: int) -> dict:
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
            ``surplus`` for the month, ``unallocated`` remainder, and
            ``is_provisional`` — true while the month is still open, because
            the figures move as new transactions land.
        """
        self.ensure_allocations()
        today = date.today()
        is_provisional = (year, month) >= (today.year, today.month)

        allocations = self.repo.get_month_allocations(year, month)
        by_goal = (
            dict(zip(allocations["goal_id"], allocations["amount"]))
            if not allocations.empty
            else {}
        )

        context = self._build_context()
        direct = context["direct"].get((year, month), {})
        surplus = context["surplus"].get((year, month), 0.0)

        rows = []
        for goal in self._goals_in_order():
            allocated = float(by_goal.get(goal.id, 0.0))
            contributed = float(direct.get(goal.id, 0.0))
            if allocated == 0 and contributed == 0:
                continue
            rows.append(
                {
                    "goal_id": goal.id,
                    "name": goal.name,
                    "priority": goal.priority,
                    "status": goal.status,
                    "allocated": round(allocated, 2),
                    "contributed": round(contributed, 2),
                    "total": round(allocated + contributed, 2),
                }
            )

        total = sum(row["total"] for row in rows)
        return {
            "year": year,
            "month": month,
            "goals": rows,
            "total_allocated": round(total, 2),
            "surplus": round(surplus, 2),
            "unallocated": round(max(0.0, surplus - total), 2),
            "is_provisional": is_provisional,
        }

    def create(self, **fields) -> dict:
        """Create a new savings goal at the bottom of the waterfall."""
        fields.setdefault("priority", self.repo.next_priority())
        if not fields.get("start_month"):
            today = date.today()
            fields["start_month"] = _month_str((today.year, today.month))
        self._validate_month(fields.get("start_month"), "start_month")
        self.repo.add(**{k: v for k, v in fields.items() if v is not None})
        return self._after_write()

    def update(self, goal_id: int, **fields) -> dict:
        """Update an existing savings goal."""
        if "start_month" in fields:
            self._validate_month(fields["start_month"], "start_month")
        try:
            self.repo.update(goal_id, **fields)
        except ValueError:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        return self._after_write()

    def delete(self, goal_id: int) -> None:
        """Delete a savings goal and everything attached to it."""
        try:
            self.repo.delete(goal_id)
        except ValueError:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")

    def reorder(self, ordered_ids: list[int]) -> list[dict]:
        """Set the waterfall order; the first id is funded first.

        New priorities take effect from the next allocation run forward.
        Already-written months keep their amounts until an explicit
        :meth:`rebuild` restates them.
        """
        known = set(self.repo.get_all()["id"]) if not self.repo.get_all().empty else set()
        unknown = [gid for gid in ordered_ids if gid not in known]
        if unknown:
            raise EntityNotFoundException(f"Unknown savings goal ids: {unknown}")
        self.repo.set_priorities(ordered_ids)
        return self._after_write()

    def close(self, goal_id: int) -> dict:
        """Close a goal by hand, freezing its allocation history."""
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        today = date.today()
        self.repo.update(
            goal_id,
            status=GOAL_STATUS_CLOSED,
            closed_month=_month_str((today.year, today.month)),
        )
        return self._after_write()

    def reopen(self, goal_id: int) -> dict:
        """Reopen a closed goal so it absorbs surplus again."""
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.repo.update(goal_id, status=GOAL_STATUS_ACTIVE, closed_month=None)
        return self._after_write()

    # ------------------------------------------------------------------
    # Transaction links
    # ------------------------------------------------------------------

    def link_transaction(
        self,
        goal_id: int,
        source_type: str,
        source_id: int,
        source_table: str,
        link_type: str,
    ) -> dict:
        """Attach a transaction to a goal as a contribution or a utilization."""
        if link_type not in (LINK_CONTRIBUTION, LINK_UTILIZATION):
            raise ValidationException(
                f"link_type must be '{LINK_CONTRIBUTION}' or '{LINK_UTILIZATION}'"
            )
        if not self.repo.get(goal_id):
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.repo.upsert_link(
            goal_id, source_type, source_id, source_table, link_type
        )
        return self._after_write()

    def unlink_transaction(self, link_id: int) -> dict:
        """Detach a transaction from its goal."""
        try:
            self.repo.delete_link(link_id)
        except ValueError:
            raise EntityNotFoundException(f"Savings goal link {link_id} not found")
        return self._after_write()

    def get_links(self, goal_id: int | None = None) -> list[dict]:
        """Return transaction links, optionally scoped to one goal."""
        links = self.repo.get_links(goal_id)
        if links.empty:
            return []
        links = links.replace({np.nan: None})
        return links.to_dict("records")

    # ------------------------------------------------------------------
    # Allocation engine
    # ------------------------------------------------------------------

    def ensure_allocations(self) -> None:
        """Fill in any months the ledger is missing and refresh the open month.

        Closed months already on record are left exactly as they are — this is
        what keeps a later priority change from silently restating history.
        The current month is always recomputed, since it is provisional until
        the month ends.
        """
        plan = self._simulate(recompute_from=None)
        self._persist(plan)

    def rebuild(self, from_month: str | None = None, dry_run: bool = False) -> dict:
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
            out of them.
        """
        start = _month_key(from_month) if from_month else None
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
            was, now = round(before.get(goal_id, 0.0), 2), round(after.get(goal_id, 0.0), 2)
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

    def _simulate(self, recompute_from: tuple[int, int] | None) -> _Plan:
        """Walk the timeline month by month, allocating surplus to goals.

        Parameters
        ----------
        recompute_from : tuple or None
            When a ``(year, month)`` tuple, every month from there on is
            recomputed. When ``None``, only months with no ledger rows yet —
            plus the always-provisional current month — are computed, and
            everything else is replayed from what is already stored.

        Returns
        -------
        _Plan
            Computed allocations plus the funded/utilized/closed state each
            goal ends the timeline in.
        """
        goals = self._goals_in_order()
        plan = _Plan()
        if not goals:
            return plan

        context = self._build_context()
        stored = self._stored_allocations()

        today = date.today()
        current = (today.year, today.month)
        starts = [_month_key(g.start_month) or current for g in goals]
        first_month = min(starts)
        if first_month > current:
            return plan

        funded = {g.id: float(g.opening_balance or 0.0) for g in goals}
        utilized = {g.id: 0.0 for g in goals}
        # A goal closed by the user is frozen from the outset; one that fills
        # and is fully spent closes partway through the walk.
        frozen = {g.id: g.status == GOAL_STATUS_CLOSED for g in goals}
        start_of = dict(zip((g.id for g in goals), starts))

        plan.surplus = context["surplus"]

        for year, month in _iter_months(first_month, current):
            key = (year, month)
            # The open month is always restated (it is provisional), as is
            # everything inside an explicit rebuild range. Every other month is
            # history: existing rows stand, and only goals with no row yet may
            # draw on whatever the month left unallocated.
            recompute = (
                recompute_from is not None and key >= recompute_from
            ) or key == current

            pool = max(0.0, context["surplus"].get(key, 0.0))

            # A closed goal keeps whatever it was given; that money is spoken
            # for, so it leaves the pool before anyone else draws on it.
            for goal in goals:
                if frozen[goal.id]:
                    amount = stored.get((goal.id, year, month), 0.0)
                    if amount:
                        funded[goal.id] += amount
                        pool -= amount

            # Contributions are derived from transactions rather than stored,
            # so they are always current — and they claim their share of the
            # pool before the waterfall runs.
            for goal_id, amount in context["direct"].get(key, {}).items():
                if goal_id in funded and not frozen[goal_id]:
                    funded[goal_id] += amount
                    pool -= amount
            pool = max(0.0, pool)

            if not recompute:
                for goal in goals:
                    if frozen[goal.id]:
                        continue
                    amount = stored.get((goal.id, year, month))
                    if amount is not None:
                        funded[goal.id] += amount
                        pool -= amount
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
                need = float(goal.target_amount or 0.0) - funded[goal.id]
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

            # Money spent back out of a goal lands after that month's funding,
            # and never reduces the target — it is utilization, not a refund.
            for goal_id, amount in context["utilized"].get(key, {}).items():
                if goal_id in utilized:
                    utilized[goal_id] += amount

            for goal in goals:
                if frozen[goal.id]:
                    continue
                target = float(goal.target_amount or 0.0)
                achieved = target > 0 and funded[goal.id] >= target
                if achieved and (funded[goal.id] - utilized[goal.id]) <= 0:
                    frozen[goal.id] = True
                    plan.closed_month[goal.id] = _month_str(key)

        plan.funded = funded
        plan.utilized = utilized
        return plan

    def _persist(self, plan: _Plan) -> None:
        """Write a plan's computed allocations and any auto-closures."""
        for (goal_id, year, month), amount in plan.computed.items():
            self.repo.upsert_allocation(goal_id, year, month, amount, ALLOCATION_AUTO)
        for goal_id, closed_month in plan.closed_month.items():
            goal = self.repo.get(goal_id)
            if goal and goal.status != GOAL_STATUS_CLOSED:
                self.repo.update(
                    goal_id, status=GOAL_STATUS_CLOSED, closed_month=closed_month
                )

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------

    def _build_context(self) -> dict:
        """Compute per-month surplus and per-month goal-linked amounts.

        Goal-linked transactions are pulled out of the surplus calculation
        before it runs, then reintroduced explicitly — a contribution consumes
        the pool, a utilization draws down what was set aside earlier. Leaving
        them in would deduct the same shekel twice.

        Returns
        -------
        dict
            ``surplus`` — ``{(year, month): float}``; ``direct`` and
            ``utilized`` — ``{(year, month): {goal_id: amount}}``.
        """
        df = self.transactions_service.get_data_for_analysis()
        empty = {"surplus": {}, "direct": {}, "utilized": {}}
        if df.empty:
            return empty

        source_col = TransactionsTableFields.SOURCE.value
        date_col = TransactionsTableFields.DATE.value
        amount_col = TransactionsTableFields.AMOUNT.value
        tag_col = TransactionsTableFields.TAG.value

        df = df[~df[source_col].isin(_SURPLUS_EXCLUDED_SOURCES | _PRIOR_WEALTH_SOURCES)]
        if tag_col in df.columns:
            df = df[df[tag_col] != PRIOR_WEALTH_TAG]
        if df.empty:
            return empty

        df = df.copy()
        parsed = pd.to_datetime(df[date_col], errors="coerce")
        df = df[parsed.notna()]
        if df.empty:
            return empty
        parsed = parsed[parsed.notna()]
        df["_year"] = parsed.dt.year.astype(int)
        df["_month"] = parsed.dt.month.astype(int)

        goal_of = self._goal_by_transaction(df)
        df["_goal_id"] = [goal_of.get(k, (None, None))[0] for k in self._row_keys(df)]
        df["_link_type"] = [goal_of.get(k, (None, None))[1] for k in self._row_keys(df)]

        linked = df[df["_goal_id"].notna()]
        unlinked = df[df["_goal_id"].isna()]

        surplus: dict[tuple[int, int], float] = {}
        if not unlinked.empty:
            masks = transactions_masks(unlinked)
            income = unlinked[masks["income"]].groupby(["_year", "_month"])[amount_col].sum()
            expenses = unlinked[masks["expenses"]].groupby(["_year", "_month"])[amount_col].sum()
            investments = (
                unlinked[masks["investments"]].groupby(["_year", "_month"])[amount_col].sum()
            )
            # Expenses and investments are negative in the raw convention, so
            # summing all three straight through already nets them out.
            combined = income.add(expenses, fill_value=0).add(investments, fill_value=0)
            surplus = {(int(y), int(m)): float(v) for (y, m), v in combined.items()}

        direct: dict[tuple[int, int], dict[int, float]] = {}
        utilized: dict[tuple[int, int], dict[int, float]] = {}
        for _, row in linked.iterrows():
            key = (int(row["_year"]), int(row["_month"]))
            goal_id = int(row["_goal_id"])
            amount = abs(float(row[amount_col]))
            bucket = direct if row["_link_type"] == LINK_CONTRIBUTION else utilized
            bucket.setdefault(key, {})
            bucket[key][goal_id] = bucket[key].get(goal_id, 0.0) + amount

        return {"surplus": surplus, "direct": direct, "utilized": utilized}

    @staticmethod
    def _row_keys(df: pd.DataFrame) -> list[tuple]:
        """Build ``(source_table, unique_id, split_id)`` keys for each row.

        ``unique_id`` is a per-table auto-increment, so it only identifies a
        transaction when paired with its table — see
        ``.claude/rules/backend_repositories.md``.
        """
        source_col = TransactionsTableFields.SOURCE.value
        uid_col = TransactionsTableFields.UNIQUE_ID.value
        split_col = TransactionsTableFields.SPLIT_ID.value
        splits = (
            df[split_col] if split_col in df.columns else pd.Series([None] * len(df))
        )
        return [
            (src, uid, None if pd.isna(sid) else int(sid))
            for src, uid, sid in zip(df[source_col], df[uid_col], splits)
        ]

    def _goal_by_transaction(self, df: pd.DataFrame) -> dict[tuple, tuple[int, str]]:
        """Map each linked transaction key to its ``(goal_id, link_type)``.

        Explicit per-transaction links win over a goal's category/tag rule, so
        a single correction on one transaction always beats the broad rule.
        """
        mapping: dict[tuple, tuple[int, str]] = {}

        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        keys = self._row_keys(df)

        for goal in self._goals_in_order():
            if not goal.contribution_category:
                continue
            matches = df[category_col] == goal.contribution_category
            tags = self._split_tags(goal.contribution_tags)
            if tags and tags != [_ALL_TAGS] and tag_col in df.columns:
                matches &= df[tag_col].isin(tags)
            for key, matched in zip(keys, matches):
                if matched:
                    mapping[key] = (goal.id, LINK_CONTRIBUTION)

        links = self.repo.get_links()
        if not links.empty:
            for _, link in links.iterrows():
                if link["source_type"] == "split":
                    key = (None, None, int(link["source_id"]))
                    for candidate in keys:
                        if candidate[2] == key[2]:
                            mapping[candidate] = (
                                int(link["goal_id"]), link["link_type"]
                            )
                else:
                    for candidate in keys:
                        if (
                            candidate[0] == link["source_table"]
                            and str(candidate[1]) == str(link["source_id"])
                        ):
                            mapping[candidate] = (
                                int(link["goal_id"]), link["link_type"]
                            )
        return mapping

    @staticmethod
    def _split_tags(tags: str | None) -> list[str]:
        """Split the semicolon-separated tag string budgets also use."""
        if not tags:
            return []
        return [t.strip() for t in str(tags).split(";") if t.strip()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _goals_in_order(self) -> list:
        """Return every goal (active and closed) in waterfall order."""
        df = self.repo.get_all()
        if df.empty:
            return []
        ids = df.sort_values(["priority", "id"])["id"].tolist()
        return [self.repo.get(int(i)) for i in ids]

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

    def _after_write(self) -> list[dict]:
        """Refresh the ledger after a mutation and return the enriched goals."""
        self.ensure_allocations()
        return self._enriched_goals()

    @staticmethod
    def _validate_month(value, field_name: str) -> None:
        """Reject a month string the engine could not parse."""
        if value is not None and _month_key(value) is None:
            raise ValidationException(
                f"{field_name} must look like 'YYYY-MM', got {value!r}"
            )

    def _enriched_goals(self) -> list[dict]:
        """Build the API payload for every goal from the current ledger."""
        goals = self._goals_in_order()
        if not goals:
            return []

        allocations = self.repo.get_allocations()
        totals: dict[int, float] = {}
        history: dict[int, list[dict]] = {}
        if not allocations.empty:
            for row in allocations.sort_values(["year", "month"]).itertuples(index=False):
                goal_id = int(row.goal_id)
                totals[goal_id] = totals.get(goal_id, 0.0) + float(row.amount)
                history.setdefault(goal_id, []).append(
                    {
                        "month": _month_str((int(row.year), int(row.month))),
                        "amount": round(float(row.amount), 2),
                    }
                )

        context = self._build_context()
        contributed: dict[int, float] = {}
        utilized: dict[int, float] = {}
        for bucket, sink in ((context["direct"], contributed), (context["utilized"], utilized)):
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
                    if entry["month"] == _month_str(current)
                ),
                0.0,
            )
            for goal_id, rows in history.items()
        }

        return [
            self._enrich(goal, totals, contributed, utilized, history, provisional)
            for goal in goals
        ]

    @staticmethod
    def _enrich(
        goal,
        totals: dict,
        contributed: dict,
        utilized: dict,
        history: dict,
        provisional: dict,
    ) -> dict:
        """Assemble one goal's derived progress metrics."""
        target = float(goal.target_amount or 0.0)
        opening = float(goal.opening_balance or 0.0)
        allocated = float(totals.get(goal.id, 0.0))
        contributions = float(contributed.get(goal.id, 0.0))
        spent = float(utilized.get(goal.id, 0.0))

        funded = opening + allocated + contributions
        available = funded - spent
        remaining = max(0.0, target - funded)
        progress_pct = round(min(100.0, (funded / target * 100) if target > 0 else 0.0), 1)
        is_achieved = target > 0 and funded >= target

        months_remaining = None
        monthly_needed = None
        if goal.target_date and pd.notna(goal.target_date):
            today = pd.Timestamp.today().normalize()
            target_ts = pd.Timestamp(goal.target_date)
            months = (target_ts.year - today.year) * 12 + (target_ts.month - today.month)
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
            "status": goal.status,
            "closed_month": goal.closed_month,
            "notes": goal.notes,
            "allocated": round(allocated, 2),
            "contributed": round(contributions, 2),
            "utilized": round(spent, 2),
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
