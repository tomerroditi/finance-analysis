"""Monthly budget service — month-scoped rules, auto-fill, and monthly analysis."""

import calendar
from datetime import date
from typing import Any

import pandas as pd

from backend.constants.budget import (
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    PERIOD_MONTHLY,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.services.budget import ledger
from backend.services.budget.core import BudgetService, _auto_fill_lock

# Auto-fill copies the newest month's rules into every empty month up to the
# one being viewed. Past this many months of gap the target is almost
# certainly a mistyped year (2206 for 2026), so only the requested month is
# filled rather than minting a rule set for every month in between.
MAX_AUTO_FILL_GAP_MONTHS = 12


class MonthlyBudgetService(BudgetService):
    """Service for managing monthly budget rules."""

    def get_all_rules(self) -> pd.DataFrame:
        """Get all monthly budget rules (period_type == 'monthly')."""
        rules = super().get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == PERIOD_MONTHLY]

    def delete_rules_by_month(self, year: int, month: int) -> None:
        """
        Delete all budget rules for a specific month.

        Parameters
        ----------
        year : int
            Calendar year of the rules to delete.
        month : int
            Calendar month (1–12) of the rules to delete.
        """
        self.budget_repository.delete_by_month(year, month)

    def copy_last_month_rules(
        self, year: int, month: int, budget_rules: pd.DataFrame | None = None
    ) -> str | None:
        """
        Copy budget rules from the previous month to the target month.

        Deletes any existing rules for the target month first, then
        recreates them from the prior month's rules.

        Parameters
        ----------
        year : int
            Target year to copy rules into.
        month : int
            Target month (1–12) to copy rules into.
        budget_rules : pd.DataFrame, optional
            All existing monthly budget rules (from ``get_all_rules``); read
            here when omitted.

        Returns
        -------
        str or None
            A summary message such as ``"Copied N rules from YYYY-M"`` — where
            ``N`` counts the rules actually created in the target month, not
            the source month's rules (a rule whose every tag is claimed by a
            yearly rule is skipped) — or ``None`` if the prior month has no
            rules.
        """
        self._last_copy_skipped = []
        if budget_rules is None:
            budget_rules = self.get_all_rules()
        last_month = month - 1 if month != 1 else 12
        last_year = year if month != 1 else year - 1

        rules_to_copy = budget_rules[
            (budget_rules[YEAR] == last_year) & (budget_rules[MONTH] == last_month)
        ]

        if rules_to_copy.empty:
            return None

        self.delete_rules_by_month(year, month)

        self._last_copy_skipped = self._copy_rules(
            rules_to_copy,
            conflict_period_type=PERIOD_YEARLY,
            target_year=year,
            target_month=month,
            kind=PERIOD_MONTHLY,
            total_budget_passthrough=True,
        )

        created = len(self.get_month_rules(year, month))
        return f"Copied {created} rules from {last_year}-{last_month}"

    def auto_fill_empty_months(
        self, current_year: int, current_month: int, budget_rules: pd.DataFrame
    ) -> str | None:
        """
        Auto-fill empty months from the latest month with rules up to the current one.

        Finds the most recent month (before or equal to *current_month*) that
        has budget rules. Then copies those rules into every empty month from
        the source month + 1 through *current_month* inclusive. When the gap
        exceeds ``MAX_AUTO_FILL_GAP_MONTHS`` only *current_month* itself is
        filled, so a mistyped far-future year can't mint hundreds of months.

        Parameters
        ----------
        current_year : int
            The current calendar year.
        current_month : int
            The current calendar month (1-12).
        budget_rules : pd.DataFrame
            All existing monthly budget rules (from ``get_all_rules``).

        Returns
        -------
        str or None
            A human-readable source month string (e.g. ``"January 2026"``) if
            rules were copied, or ``None`` if the current month already has
            rules or no source month was found.

        Notes
        -----
        Serialized via ``_auto_fill_lock`` so concurrent threadpool requests
        (the active month plus adjacent-month prefetches) don't each copy the
        source month and duplicate rules. The passed-in ``budget_rules`` is a
        snapshot taken before the lock, so we re-read it fresh inside the lock
        to observe rules a request that won the race already committed.

        With no earlier month to copy from there is nothing to fill, so it
        returns before taking the lock. The re-read starts with a
        ``rollback()``, and every rollback discards the cross-request
        ``data_cache`` — a household without monthly rules used to throw the
        whole cache away on every visit to its current month.
        """
        self._auto_fill_skipped = []
        if self._auto_fill_source(current_year, current_month, budget_rules) is None:
            return None
        with _auto_fill_lock:
            # Drop this session's read snapshot and re-read committed state so a
            # request that lost the race sees the month already filled.
            self.db.rollback()
            budget_rules = self.get_all_rules()

            current_rules = self.get_month_rules(
                current_year, current_month, budget_rules
            )
            if not current_rules.empty:
                return None

            return self._auto_fill_empty_months_locked(
                current_year, current_month, budget_rules
            )

    def _auto_fill_empty_months_locked(
        self, current_year: int, current_month: int, budget_rules: pd.DataFrame
    ) -> str | None:
        """Fill empty months from the latest prior month with rules.

        Must be called while holding ``_auto_fill_lock`` with a freshly-read
        ``budget_rules``. See :meth:`auto_fill_empty_months`.
        """
        source = self._auto_fill_source(current_year, current_month, budget_rules)
        if source is None:
            return None
        source_year, source_month = source

        source_rules = self.get_month_rules(source_year, source_month, budget_rules)

        # Iterate from source+1 to current month, filling empty months. A gap
        # wider than the cap fills only the requested month.
        skipped: list[str] = list(getattr(self, "_auto_fill_skipped", []))
        gap = (current_year * 12 + current_month) - (source_year * 12 + source_month)
        if gap > MAX_AUTO_FILL_GAP_MONTHS:
            y, m = current_year, current_month - 1
            if m == 0:
                y, m = current_year - 1, 12
        else:
            y, m = source_year, source_month
        while True:
            if m == 12:
                m = 1
                y += 1
            else:
                m += 1

            month_rules = self.get_month_rules(y, m, budget_rules)
            if month_rules.empty:
                skipped.extend(
                    self._copy_rules(
                        source_rules,
                        conflict_period_type=PERIOD_YEARLY,
                        target_year=y,
                        target_month=m,
                        kind=PERIOD_MONTHLY,
                        total_budget_passthrough=True,
                    )
                )

            if y == current_year and m == current_month:
                break

        self._auto_fill_skipped = skipped
        source_month_name = calendar.month_name[source_month]
        return f"{source_month_name} {source_year}"

    @staticmethod
    def _auto_fill_source(
        year: int, month: int, budget_rules: pd.DataFrame
    ) -> tuple[int, int] | None:
        """Return the latest month before ``year``/``month`` that has monthly rules.

        Parameters
        ----------
        year, month : int
            The month auto-fill would fill.
        budget_rules : pd.DataFrame
            Every budget rule.

        Returns
        -------
        tuple[int, int] or None
            ``(year, month)`` of the month auto-fill copies from, or ``None``
            when no earlier month has rules.
        """
        if budget_rules.empty:
            return None
        monthly_rules = budget_rules.dropna(subset=[YEAR, MONTH])
        before = monthly_rules[
            (monthly_rules[YEAR] < year)
            | ((monthly_rules[YEAR] == year) & (monthly_rules[MONTH] < month))
        ]
        if before.empty:
            return None
        latest = before.loc[(before[YEAR] * 12 + before[MONTH]).idxmax()]
        return int(latest[YEAR]), int(latest[MONTH])

    def effective_total_budget(
        self, year: int, month: int, budget_rules: pd.DataFrame | None = None
    ) -> float:
        """Return the month's Total Budget, or the one auto-fill would give it.

        Read-only: a month with rules answers with its own Total Budget rule
        (``0.0`` without one). An empty current or future month answers with
        the Total Budget of the latest earlier month that has rules — exactly
        what :meth:`auto_fill_empty_months` would copy in — without writing
        it. An empty past month has no budget, as auto-fill never touches the
        past.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        budget_rules : pd.DataFrame, optional
            All monthly rules; read here when omitted.

        Returns
        -------
        float
            The month's total budget.
        """
        if budget_rules is None:
            budget_rules = self.get_all_rules()
        rules = (
            budget_rules.dropna(subset=[YEAR, MONTH])
            if not budget_rules.empty
            else budget_rules
        )
        if rules.empty:
            return 0.0
        month_rules = rules[(rules[YEAR] == year) & (rules[MONTH] == month)]
        if month_rules.empty:
            today = date.today()
            if (year, month) < (today.year, today.month):
                return 0.0
            earlier = rules[rules[YEAR] * 12 + rules[MONTH] < year * 12 + month]
            if earlier.empty:
                return 0.0
            latest = (earlier[YEAR] * 12 + earlier[MONTH]).max()
            month_rules = earlier[earlier[YEAR] * 12 + earlier[MONTH] == latest]
        total = month_rules[month_rules[CATEGORY] == TOTAL_BUDGET]
        return float(total.iloc[0][AMOUNT] or 0.0) if not total.empty else 0.0

    def get_month_rules(
        self, year: int, month: int, budget_rules: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        """
        Get all budget rules for a specific month.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        budget_rules : pd.DataFrame, optional
            Pre-fetched rules DataFrame. If ``None``, ``get_all_rules`` is called.

        Returns
        -------
        pd.DataFrame
            Budget rules filtered to the given year and month.
        """
        if budget_rules is None:
            budget_rules = self.get_all_rules()
        return budget_rules[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]

    def create_rule(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        month: int,
        year: int,
    ) -> None:
        """
        Create a monthly budget rule; see :func:`~backend.services.budget.rules.rule_error`.

        Parameters
        ----------
        name : str
            Human-readable label for the rule.
        amount : float
            Budget limit amount.
        category : str
            Category the rule applies to, or ``"Total Budget"`` for the
            month's cap.
        tags : str or list[str]
            Tags the rule covers (string or list; stored as semicolon-separated).
        month : int
            Calendar month (1–12).
        year : int
            Calendar year.

        Raises
        ------
        ValidationException
            If the rule fails validation.
        """
        self.rules.create(PERIOD_MONTHLY, name, amount, category, tags, year, month)

    def get_budget_trend(
        self,
        year: int,
        month: int,
        months: int = 12,
        include_split_parents: bool = False,
    ) -> list[dict[str, Any]]:
        """Return budget-vs-actual totals for the trailing ``months`` calendar months.

        One call in place of one ``get_monthly_analysis`` request per month.
        The budget page renders a 12-month sparkline, so the page used to open
        twelve concurrent requests for it — and because every successful
        mutation invalidates the whole query cache, all twelve fired again on
        each one. They are individually cheap but collectively saturating:
        ``/budget/overview`` answers in ~0.5 s alone and ~12 s alongside them,
        which is long enough for the Overview to keep showing a closed project
        after it has been reopened.

        Deliberately built on rule totals (:meth:`_month_totals`) rather than
        ``get_monthly_analysis`` or even the full rule view: the sparkline
        needs only each rule's spend, while the view also lists every claimed
        transaction and the analysis additionally assembles project spending,
        savings-goal allocations and pending refunds.

        **Read-only, and therefore not a drop-in for the analysis endpoint.**
        ``get_monthly_analysis`` auto-fills an empty current/future month by
        copying the previous month's rules; this does not, so a brand-new
        month reports zeros here until that happens. The caller owns that
        month's figures anyway — it is the month the page is displaying — so
        the frontend hook overlays them from the analysis query it already
        holds. Two writers racing to auto-fill the same month would be the
        alternative, and this endpoint has no business writing.

        Parameters
        ----------
        year : int
            Year of the last month in the series.
        month : int
            Month (1–12) of the last month in the series, inclusive.
        months : int, optional
            How many calendar months the series spans, ending at
            ``year``/``month``. Default 12.
        include_split_parents : bool, optional
            When ``True``, include split parents alongside their children.

        Returns
        -------
        list[dict]
            One entry per month, oldest first, each with ``year``, ``month``,
            ``budget`` (the "Total Budget" row's configured cap), ``actual``
            (that row's spend, sign-normalised), ``rules`` mapping each rule
            name to its spend and ``limits`` mapping each rule name to the
            cap it carried that month.
        """
        claims = ledger.of_kind(self.get_claims(), *ledger.MONTHLY_POOL)
        budget_rules = self.get_all_rules()
        series: list[dict[str, Any]] = []
        for offset in range(months - 1, -1, -1):
            # Month arithmetic through a zero-based absolute index, so
            # stepping back across a year boundary needs no special case.
            absolute = (year * 12 + month - 1) - offset
            point_year, point_month = divmod(absolute, 12)
            point_month += 1
            view = (
                self._month_totals(claims, budget_rules, point_year, point_month) or []
            )

            # The "Total Budget" row is the source of truth for the headline
            # pair, exactly as the monthly gauge reads it. Summing the
            # per-category rules would undercount both the budget (it ignores
            # headroom no rule claims) and the actual (it drops the
            # "Other Expenses" catch-all).
            total = next(
                (item for item in view if item["rule"][NAME] == TOTAL_BUDGET),
                None,
            )

            # Rules are keyed by NAME, not id: a month auto-filled from its
            # predecessor gets freshly created rows, so the same envelope
            # carries a different id in every month.
            rules = {
                item["rule"][NAME]: max(item.get("current_amount") or 0, 0)
                for item in view
            }

            # The limit each rule carried *that* month, so the sparkline can
            # draw its reference against the month it belongs to. A rule is
            # a fresh row per month and its cap is editable, so plotting
            # every month against today's limit misreports history: a month
            # that ran 1,800 against an 1,800 budget reads as an overspend
            # once the envelope is cut to 1,500. A name missing here simply
            # had no envelope that month.
            limits = {
                item["rule"][NAME]: item["rule"].get(AMOUNT) or 0 for item in view
            }

            series.append(
                {
                    "year": point_year,
                    "month": point_month,
                    "budget": (total or {}).get("rule", {}).get(AMOUNT) or 0,
                    "actual": abs((total or {}).get("current_amount") or 0),
                    "rules": rules,
                    "limits": limits,
                }
            )
        return series

    def get_monthly_analysis(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict[str, Any]:
        """
        Get full monthly budget analysis combining budget view, project spending, and pending refunds.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``rules`` – list of budget rule view dicts (from ``get_monthly_budget_view``),
              or empty list if no rules are defined.
            - ``project_spending`` – dict with a ``projects`` list summarising
              project spend for the month (from ``get_monthly_project_spending_summary``).
            - ``pending_refunds`` – dict with ``items`` (pending refund list) and
              ``total_expected`` (sum of expected amounts).
            - ``savings_goals`` – what moved into and out of each goal that
              month (from ``SavingsGoalService.get_month``).
            - ``copied_from`` – source month name if rules were auto-filled,
              or ``None``.
            - ``skipped_yearly_conflicts`` – tag names dropped from an
              auto-fill copy because they are claimed by a yearly rule for
              this year.
            - ``uncategorized_count`` / ``uncategorized_amount`` – how many
              rows of the month's monthly pool carry no category, and their
              gross absolute total (``0`` without a Total Budget rule).

            The Total Budget entry's ``data`` is empty whenever another entry
            exists: every pool row is already listed under the rule that
            claimed it or under Other Expenses, so the client builds the
            month's list as their union rather than receiving it twice.
        """
        copied_from = None
        today = date.today()

        # Auto-fill empty months from the latest prior month with rules, for the
        # current month or any future month being viewed. Past months are left
        # untouched so historical budgets are never rewritten.
        if (year, month) >= (today.year, today.month):
            budget_rules = self.get_all_rules()
            current_rules = self.get_month_rules(year, month, budget_rules)
            if current_rules.empty:
                copied_from = self.auto_fill_empty_months(year, month, budget_rules)

        view = self.get_monthly_budget_view(year, month, include_split_parents)
        uncategorized_count, uncategorized_amount = _strip_total_budget_rows(view)
        project_summary = self.get_monthly_project_spending_summary(
            year, month, include_split_parents
        )

        # Savings-goal allocations ride along with the analysis rather than
        # getting their own endpoint call from the budget page. The section
        # renders inside this view, so a separate per-month request would just
        # add another participant to every refresh of the same screen.
        from backend.services.savings_goals import SavingsGoalService

        savings_goals = SavingsGoalService(self.db).get_month(year, month)

        pending_refunds = self.pending_refunds_service.get_all_pending(status="pending")
        budget_adjustment = self.pending_refunds_service.get_budget_adjustment(
            year, month
        )

        skipped_yearly = sorted(set(getattr(self, "_auto_fill_skipped", [])))

        return {
            "rules": view or [],
            "project_spending": project_summary,
            "pending_refunds": {
                "items": pending_refunds,
                "total_expected": budget_adjustment,
            },
            "savings_goals": savings_goals,
            "copied_from": copied_from,
            "skipped_yearly_conflicts": skipped_yearly,
            "uncategorized_count": uncategorized_count,
            "uncategorized_amount": uncategorized_amount,
        }

    def get_monthly_budget_view(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> list[dict[str, Any]] | None:
        """
        Compute budget rule usage view for a given month.

        Reads the claim ledger (:meth:`get_claims`): each transaction counts
        toward exactly one rule — the most specific one that matches (see
        :func:`ledger.claim_order`) — so a category's ``all_tags`` rule reports
        only the spend its sibling tag rules leave unclaimed. Rows are bucketed
        by budget month, and project- and yearly-owned rows are not in the
        monthly pool.
        If spend remains after all rules are matched, an ``"Other Expenses"`` entry
        is appended using the unallocated portion of the total budget.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        list[dict] or None
            ``None`` if no budget rules exist for the month. Otherwise a list of
            rule view dicts, each with keys:

            - ``rule`` – the budget rule dict.
            - ``current_amount`` – actual spend matched to this rule (positive float).
            - ``data`` – list of transaction dicts matched to this rule.
            - ``allow_edit`` – whether the rule amount can be changed.
            - ``allow_delete`` – whether the rule can be deleted.
        """
        return self._month_view(self.get_claims(), self.get_all_rules(), year, month)

    @staticmethod
    def _month_view(
        claims: pd.DataFrame, budget_rules: pd.DataFrame, year: int, month: int
    ) -> list[dict[str, Any]] | None:
        """Build one month's rule view from the claim ledger.

        The Total Budget row carries the month's whole monthly pool — every row
        a monthly rule claimed plus every row none did — so it always agrees
        with the Overview's ``monthly_spent``.
        """
        if budget_rules.empty:
            return None
        rules = budget_rules[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]
        if rules.empty:
            return None

        pool = ledger.of_kind(
            ledger.in_budget_month(claims, year, month), *ledger.MONTHLY_POOL
        )
        view = []

        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            view.append(
                {
                    "rule": total_rule.iloc[0].to_dict(),
                    "current_amount": ledger.spent(pool),
                    "data": ledger.transaction_records(pool),
                    "allow_edit": True,
                    "allow_delete": False,
                }
            )
            rules = rules.loc[~rules.index.isin(total_rule.index)]

        for _, rule in rules.iterrows():
            claimed = ledger.of_rule(pool, rule[ID])
            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": ledger.spent(claimed),
                    "data": ledger.transaction_records(claimed),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

        unclaimed = ledger.of_kind(pool, ledger.KIND_OTHER)
        if not unclaimed.empty and not rules.empty and not total_rule.empty:
            total_alloc = rules[AMOUNT].sum()
            # When per-category rules sum to more than the total budget, the
            # remainder is negative — surface it as 0 (no headroom) rather than
            # a meaningless negative budget. The bar then correctly reads as
            # "any unbudgeted spend is over budget".
            total_amt = max(total_rule.iloc[0][AMOUNT] - total_alloc, 0.0)
            view.append(
                {
                    "rule": {
                        NAME: "Other Expenses",
                        AMOUNT: total_amt,
                        CATEGORY: "Other Expenses",
                        TAGS: "Other Expenses",
                        ID: f"{year}{month}_Other_Expenses",
                    },
                    "current_amount": ledger.spent(unclaimed),
                    "data": ledger.transaction_records(unclaimed),
                    "allow_edit": False,
                    "allow_delete": False,
                }
            )

        return view

    @staticmethod
    def _month_totals(
        claims: pd.DataFrame, budget_rules: pd.DataFrame, year: int, month: int
    ) -> list[dict[str, Any]] | None:
        """Return :meth:`_month_view`'s entries without their transaction lists.

        The trend and the alerts read only each rule's spend, and listing every
        claimed row (``ledger.transaction_records``) was most of what building
        the full view cost them. Every entry carries the same ``rule``,
        ``current_amount``, ``allow_edit`` and ``allow_delete`` as the view's,
        summed over the same rows in the same order, so the figures are
        identical to the last bit.

        Parameters
        ----------
        claims : pd.DataFrame
            The claim ledger, or any slice of it that still holds every
            monthly-pool row (the trend narrows it to the pool once).
        budget_rules : pd.DataFrame
            Every budget rule.
        year, month : int
            The budget month.

        Returns
        -------
        list[dict] or None
            ``None`` when the month has no rules, else one entry per rule,
            Total Budget first and ``"Other Expenses"`` last when present.
        """
        if budget_rules.empty:
            return None
        rules = budget_rules[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]
        if rules.empty:
            return None

        pool = ledger.of_kind(
            ledger.in_budget_month(claims, year, month), *ledger.MONTHLY_POOL
        )
        totals: list[dict[str, Any]] = []
        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            totals.append(
                {
                    "rule": total_rule.iloc[0].to_dict(),
                    "current_amount": ledger.spent(pool),
                    "allow_edit": True,
                    "allow_delete": False,
                }
            )
            rules = rules.loc[~rules.index.isin(total_rule.index)]

        for _, rule in rules.iterrows():
            totals.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": ledger.spent(ledger.of_rule(pool, rule[ID])),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

        unclaimed = ledger.of_kind(pool, ledger.KIND_OTHER)
        if not unclaimed.empty and not rules.empty and not total_rule.empty:
            totals.append(
                {
                    "rule": {
                        NAME: "Other Expenses",
                        AMOUNT: max(
                            total_rule.iloc[0][AMOUNT] - rules[AMOUNT].sum(), 0.0
                        ),
                        CATEGORY: "Other Expenses",
                        TAGS: "Other Expenses",
                        ID: f"{year}{month}_Other_Expenses",
                    },
                    "current_amount": ledger.spent(unclaimed),
                    "allow_edit": False,
                    "allow_delete": False,
                }
            )
        return totals

    def get_monthly_project_transactions(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> pd.DataFrame | None:
        """
        Get expense transactions belonging to project categories for a specific month.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        pd.DataFrame or None
            Filtered transactions DataFrame, or ``None`` if there are no project
            categories or no matching transactions for the month.
        """
        rows = ledger.of_kind(
            ledger.in_budget_month(self.get_claims(), year, month), ledger.KIND_PROJECT
        )
        return rows if not rows.empty else None

    def get_monthly_project_spending_summary(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict[str, Any]:
        """
        Get a summary of project spending for a month, grouped by project category.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``projects`` – list of per-project dicts with ``category``, ``spent``,
              and ``transactions`` keys. Empty list if no project transactions exist.
            - ``total_spent`` – sum of spend across all projects (only present
              when at least one project transaction exists).
        """
        project_txns = self.get_monthly_project_transactions(
            year, month, include_split_parents
        )
        if project_txns is None or project_txns.empty:
            return {"projects": []}

        projects_summary = [
            {
                "category": str(project_name),
                "spent": ledger.spent(group),
                "transactions": ledger.transaction_records(
                    group.where(pd.notnull(group), None)
                ),
            }
            for project_name, group in project_txns.groupby(
                TransactionsTableFields.CATEGORY.value
            )
        ]
        return {"projects": projects_summary, "total_spent": ledger.spent(project_txns)}

    def get_current_month_alerts(
        self, warning_threshold: float = 0.8
    ) -> dict[str, Any]:
        """Return the budget alerts for today's calendar month.

        Parameters
        ----------
        warning_threshold : float, optional
            Fraction of the budget at which an alert fires; see
            :meth:`get_alerts`. Default is ``0.8``.

        Returns
        -------
        dict[str, Any]
            ``{"year": Y, "month": M, "alerts": [...]}`` for the current
            month, alerts shaped as :meth:`get_alerts` returns them.
        """
        today = date.today()
        alerts = self.get_alerts(
            today.year, today.month, warning_threshold=warning_threshold
        )
        return {"year": today.year, "month": today.month, "alerts": alerts}

    def get_alerts(
        self,
        year: int,
        month: int,
        warning_threshold: float = 0.8,
    ) -> list[dict[str, Any]]:
        """
        Identify monthly budget rules whose spend has reached a warning threshold.

        A rule is "tripped" when ``current_amount / amount`` is at or above
        ``warning_threshold``. The "Total Budget" rule and the auto-generated
        "Other Expenses" pseudo-rule are excluded — Total Budget is a roll-up
        and would double-count, and "Other Expenses" has no user-set amount.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        warning_threshold : float, optional
            Fraction of the budget at which an alert starts firing. Default is
            ``0.8`` (80%). Rules at 100% or above are tagged with severity
            ``"critical"``; rules between the warning threshold and 100% are
            tagged ``"warning"``.

        Returns
        -------
        list[dict]
            One entry per tripped rule, each with keys ``rule_id``, ``name``,
            ``category``, ``tags`` (list), ``amount`` (budget), ``spent``,
            ``percentage`` (0.0–∞, where 1.0 = exactly at budget), and
            ``severity`` (``"warning"`` or ``"critical"``). Empty list when
            no rules are tripped or no rules exist for the month.
        """
        view = self._month_totals(self.get_claims(), self.get_all_rules(), year, month)
        if view is None:
            return []

        alerts = []
        for entry in view:
            rule = entry["rule"]
            category = rule.get(CATEGORY)
            if category in (TOTAL_BUDGET, "Other Expenses"):
                continue

            amount = float(rule.get(AMOUNT) or 0)
            if amount <= 0:
                continue

            spent = float(entry.get("current_amount") or 0)
            percentage = spent / amount
            if percentage < warning_threshold:
                continue

            severity = "critical" if percentage >= 1.0 else "warning"
            alerts.append(
                {
                    "rule_id": int(rule[ID]),
                    "name": str(rule.get(NAME) or ""),
                    "category": str(category),
                    "tags": list(rule.get(TAGS) or []),
                    "amount": amount,
                    "spent": spent,
                    "percentage": percentage,
                    "severity": severity,
                }
            )

        alerts.sort(key=lambda a: a["percentage"], reverse=True)
        return alerts


def _strip_total_budget_rows(view: list[dict[str, Any]] | None) -> tuple[int, float]:
    """Empty the Total Budget entry's row list when the other entries list them.

    The Total Budget entry carries the whole monthly pool, and every row of it
    is also under the rule that claimed it or under Other Expenses — which the
    view emits whenever a Total Budget and at least one other rule exist. Sent
    twice, the pool was about half of every analysis response. A month with
    only a Total Budget rule keeps its rows, since nothing else lists them.

    Parameters
    ----------
    view : list[dict] or None
        The month's rule view (:meth:`MonthlyBudgetService.get_monthly_budget_view`),
        changed in place.

    Returns
    -------
    tuple[int, float]
        The pool's uncategorized row count and the sum of their absolute gross
        amounts, read before the rows are dropped; ``(0, 0.0)`` when the month
        has no Total Budget entry.
    """
    total = next(
        (entry for entry in view or [] if entry["rule"].get(CATEGORY) == TOTAL_BUDGET),
        None,
    )
    if total is None:
        return 0, 0.0
    amount_field = TransactionsTableFields.AMOUNT.value
    uncategorized = [
        row
        for row in total["data"]
        if not row.get(TransactionsTableFields.CATEGORY.value)
        or pd.isna(row.get(TransactionsTableFields.CATEGORY.value))
    ]
    uncategorized_amount = float(
        sum(abs(row.get(amount_field) or 0.0) for row in uncategorized)
    )
    if len(view or []) > 1:
        total["data"] = []
    return len(uncategorized), uncategorized_amount
