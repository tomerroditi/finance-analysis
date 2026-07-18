"""Monthly budget service — month-scoped rules, auto-fill, and monthly analysis."""

import calendar
from datetime import date
from typing import Optional

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
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
from backend.services.transaction_classification import EXPENSE_EXCLUDED_CATEGORIES
from backend.services.budget.core import BudgetService, _auto_fill_lock
from backend.services.budget.yearly import YearlyBudgetService


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

    def get_available_tags_for_each_category(
        self, budget_rules: pd.DataFrame
    ) -> dict[str, list[str]]:
        """
        Get tags available for new budget rules (not already fully covered).

        Removes categories and tags that are already allocated in the given
        budget rules. If a rule uses ``all_tags``, the entire category is removed.

        Parameters
        ----------
        budget_rules : pd.DataFrame
            Existing budget rules for the relevant month or project.

        Returns
        -------
        dict[str, list[str]]
            Mapping of category name to remaining available tags.
        """
        cats_n_tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        for _, rule in budget_rules.iterrows():
            used_tags = rule[TAGS]
            if used_tags == [ALL_TAGS]:
                cats_n_tags.pop(rule[CATEGORY], None)
                continue

            available_tags = cats_n_tags.get(rule[CATEGORY], [])
            available_tags = [tag for tag in available_tags if tag not in used_tags]
            if not available_tags:
                cats_n_tags.pop(rule[CATEGORY], None)
            else:
                cats_n_tags[rule[CATEGORY]] = available_tags

        return cats_n_tags

    def copy_last_month_rules(
        self, year: int, month: int, budget_rules: pd.DataFrame
    ) -> Optional[str]:
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
        budget_rules : pd.DataFrame
            All existing monthly budget rules (from ``get_all_rules``).

        Returns
        -------
        str or None
            A summary message such as ``"Copied N rules from YYYY-M"`` if
            rules were found and copied, or ``None`` if the prior month
            has no rules.
        """
        self._last_copy_skipped = []
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
            total_budget_passthrough=True,
        )

        return f"Copied {len(rules_to_copy)} rules from {last_year}-{last_month}"

    def auto_fill_empty_months(
        self, current_year: int, current_month: int, budget_rules: pd.DataFrame
    ) -> Optional[str]:
        """
        Auto-fill budget rules for empty months between the latest month with
        rules and the current month.

        Finds the most recent month (before or equal to *current_month*) that
        has budget rules. Then copies those rules into every empty month from
        the source month + 1 through *current_month* inclusive.

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
        """
        self._auto_fill_skipped = []
        with _auto_fill_lock:
            # Drop this session's read snapshot and re-read committed state so a
            # request that lost the race sees the month already filled.
            self.db.rollback()
            budget_rules = self.get_all_rules()

            # If current month already has rules, nothing to do
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
    ) -> Optional[str]:
        """Fill empty months from the latest prior month with rules.

        Must be called while holding ``_auto_fill_lock`` with a freshly-read
        ``budget_rules``. See :meth:`auto_fill_empty_months`.
        """

        # Find the latest month with rules, strictly before the current month
        monthly_rules = budget_rules.dropna(subset=[YEAR, MONTH])
        if monthly_rules.empty:
            return None

        # Filter to months before the current month
        before_current = monthly_rules[
            (monthly_rules[YEAR] < current_year)
            | (
                (monthly_rules[YEAR] == current_year)
                & (monthly_rules[MONTH] < current_month)
            )
        ]
        if before_current.empty:
            return None

        # Find the latest (year, month) pair
        before_current = before_current.copy()
        before_current["_sort"] = before_current[YEAR] * 12 + before_current[MONTH]
        max_sort = before_current["_sort"].max()
        source_row = before_current[before_current["_sort"] == max_sort].iloc[0]
        source_year = int(source_row[YEAR])
        source_month = int(source_row[MONTH])

        # Get the source rules
        source_rules = self.get_month_rules(source_year, source_month, budget_rules)

        # Iterate from source+1 to current month, filling empty months
        skipped: list[str] = list(getattr(self, "_auto_fill_skipped", []))
        y, m = source_year, source_month
        while True:
            # Advance one month
            if m == 12:
                m = 1
                y += 1
            else:
                m += 1

            # Check if this month already has rules
            month_rules = self.get_month_rules(y, m, budget_rules)
            if month_rules.empty:
                skipped.extend(
                    self._copy_rules(
                        source_rules,
                        conflict_period_type=PERIOD_YEARLY,
                        target_year=y,
                        target_month=m,
                        total_budget_passthrough=True,
                    )
                )

            if y == current_year and m == current_month:
                break

        self._auto_fill_skipped = skipped
        source_month_name = calendar.month_name[source_month]
        return f"{source_month_name} {source_year}"

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
        month: int | None = None,
        year: int | None = None,
    ) -> None:
        """
        Create a budget rule with input validation and tag normalization.

        Validates via ``validate_rule_inputs`` before persisting.

        Parameters
        ----------
        name : str
            Human-readable label for the rule.
        amount : float
            Budget limit amount.
        category : str
            Category the rule applies to.
        tags : str or list[str]
            Tags the rule covers (string or list; stored as semicolon-separated).
        month : int or None, optional
            Calendar month (1–12). ``None`` for project budgets.
        year : int or None, optional
            Calendar year. ``None`` for project budgets.

        Raises
        ------
        ValueError
            If validation fails (invalid inputs or budget cap exceeded), or if
            any tag is already claimed by a yearly rule for the same ``year``.
        """
        parsed_tags = tags.split(";") if isinstance(tags, str) else tags
        if category != TOTAL_BUDGET and self.is_category_project_owned(category):
            raise ValueError(
                f"The '{category}' category belongs to a project budget. "
                f"A monthly rule can't target a project category."
            )
        if category != TOTAL_BUDGET and year is not None:
            conflicts = self.find_conflicting_tags(
                category, parsed_tags, year, PERIOD_YEARLY
            )
            if conflicts:
                joined = ", ".join(conflicts)
                raise ValueError(
                    f"{joined} is already used by your yearly budget for {year}. "
                    f"A tag can't be in both for the same year."
                )

        budget_rules = self.get_all_rules()
        is_valid, msg = self.validate_rule_inputs(
            budget_rules, name, category, parsed_tags, amount, year, month, None
        )
        if not is_valid:
            raise ValueError(msg)

        self.add_rule(name, amount, category, tags, month, year)

    def update_rule(self, id_: int, **fields):
        """Update a monthly rule, guarding edits that would claim a yearly-owned tag.

        The ``PUT /budget/rules/{id}`` route is shared between monthly and
        project rules (both are edited through the same ``rule_id``), so this
        loads the target row through the base, unfiltered
        ``BudgetService.get_all_rules`` — ``self.get_all_rules()`` here would
        be pre-filtered to ``period_type == "monthly"`` and silently miss a
        project rule's id.

        Runs the monthly-vs-yearly conflict check when the row being edited
        is itself a monthly rule (non-null ``year``) outside the
        ``Total Budget`` category — mirroring the guard in
        :meth:`create_rule`. Also guards the opposite case: this route is
        the same one project rules are edited through (``year`` is
        ``NaN`` for a project row), so a category change on a project rule
        that targets a category already claimed by a monthly/yearly budget
        is rejected too — otherwise the invariant "a category is never both
        project-owned and budget-used" could be broken via this shared
        endpoint alone. Edits that never touch ``category``/``tags`` fall
        straight through to the base update as a no-op.

        Parameters
        ----------
        id_ : int
            ID of the budget rule to update.
        **fields
            Fields to update; see ``BudgetService.update_rule``.

        Raises
        ------
        ValueError
            If the edit would claim a tag already owned by a yearly rule for
            the same year, or (for a project rule) would move it onto a
            category already used by a monthly or yearly budget.
        """
        all_rules = BudgetService.get_all_rules(self)
        if not all_rules.empty:
            row = all_rules.loc[all_rules[ID] == id_]
            if not row.empty:
                row = row.iloc[0]
                year = row[YEAR]
                category = fields.get(CATEGORY, row[CATEGORY])
                if pd.notnull(year) and category != TOTAL_BUDGET:
                    if self.is_category_project_owned(category):
                        raise ValueError(
                            f"The '{category}' category belongs to a project "
                            f"budget. A monthly rule can't target a project category."
                        )
                    tags = fields.get(TAGS, row[TAGS])
                    parsed_tags = (
                        tags.split(";") if isinstance(tags, str) else list(tags)
                    )
                    conflicts = self.find_conflicting_tags(
                        category, parsed_tags, int(year), PERIOD_YEARLY,
                        exclude_rule_id=id_,
                    )
                    if conflicts:
                        joined = ", ".join(conflicts)
                        raise ValueError(
                            f"{joined} is already used by your yearly budget for "
                            f"{int(year)}. A tag can't be in both for the same year."
                        )
                elif pd.isnull(year) and CATEGORY in fields and category != row[CATEGORY]:
                    if self.category_used_by_monthly_or_yearly(category):
                        raise ValueError(
                            f"The '{category}' category is already used by a "
                            f"monthly or yearly budget and can't be assigned to a "
                            f"project rule."
                        )

        BudgetService.update_rule(self, id_, **fields)

    def get_monthly_analysis(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict:
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
            - ``copied_from`` – source month name if rules were auto-filled,
              or ``None``.
            - ``skipped_yearly_conflicts`` – tag names dropped from an
              auto-fill copy because they are claimed by a yearly rule for
              this year.
        """
        copied_from = None
        today = date.today()

        # Auto-fill empty months from the latest prior month with rules, for the
        # current month or any future month being viewed. Past months are left
        # untouched so historical budgets are never rewritten. This replaces the
        # old manual "Replicate previous month" action.
        if (year, month) >= (today.year, today.month):
            budget_rules = self.get_all_rules()
            current_rules = self.get_month_rules(year, month, budget_rules)
            if current_rules.empty:
                copied_from = self.auto_fill_empty_months(year, month, budget_rules)

        view = self.get_monthly_budget_view(year, month, include_split_parents)
        project_summary = self.get_monthly_project_spending_summary(
            year, month, include_split_parents
        )

        pending_refunds = self.pending_refunds_service.get_all_pending(status="pending")
        budget_adjustment = self.pending_refunds_service.get_budget_adjustment(
            year, month
        )

        skipped_yearly = sorted(set(getattr(self, "_auto_fill_skipped", [])))

        return {
            "rules": view if view else [],
            "project_spending": project_summary,
            "pending_refunds": {
                "items": pending_refunds,
                "total_expected": budget_adjustment,
            },
            "copied_from": copied_from,
            "skipped_yearly_conflicts": skipped_yearly,
        }

    def _apply_month_overrides(self, expenses: pd.DataFrame) -> pd.DataFrame:
        """
        Add ``budget_year``/``budget_month`` columns honoring month overrides.

        By default a transaction is bucketed into the month of its real
        ``date``. Transactions (or splits) with an active budget month override
        are bucketed into the override's month instead, so they leave their
        natural month and appear in the target month of the monthly budget.

        Parameters
        ----------
        expenses : pd.DataFrame
            Filtered expense transactions with a parsed ``date`` column.

        Returns
        -------
        pd.DataFrame
            Copy of ``expenses`` with ``budget_year`` and ``budget_month``
            integer columns added.
        """
        expenses = expenses.copy()
        dates = pd.to_datetime(expenses[TransactionsTableFields.DATE.value])
        budget_year = dates.dt.year
        budget_month = dates.dt.month

        overrides = self.month_override_service.get_override_map()

        tx_map = overrides["transaction"]
        if tx_map:
            # Key by (source table, unique_id): unique_id is a per-table
            # auto-increment, so the bare integer collides across tables.
            keys = pd.Series(
                list(
                    zip(
                        expenses[TransactionsTableFields.SOURCE.value],
                        expenses[TransactionsTableFields.UNIQUE_ID.value],
                    )
                ),
                index=expenses.index,
            )
            budget_year = keys.map({k: v[0] for k, v in tx_map.items()}).fillna(
                budget_year
            )
            budget_month = keys.map({k: v[1] for k, v in tx_map.items()}).fillna(
                budget_month
            )

        split_map = overrides["split"]
        if split_map and TransactionsTableFields.SPLIT_ID.value in expenses.columns:
            sid = expenses[TransactionsTableFields.SPLIT_ID.value]
            budget_year = sid.map({k: v[0] for k, v in split_map.items()}).fillna(
                budget_year
            )
            budget_month = sid.map({k: v[1] for k, v in split_map.items()}).fillna(
                budget_month
            )

        expenses["budget_year"] = budget_year.astype(int)
        expenses["budget_month"] = budget_month.astype(int)
        return expenses

    def _exclude_yearly_claimed(self, month_data: pd.DataFrame, year: int) -> pd.DataFrame:
        """Drop transactions whose (category, tag) is owned by a yearly rule for ``year``.

        Yearly-managed tags are mutually exclusive with monthly rules, so their
        spend must not leak into the monthly view's per-rule matching or the
        synthetic "Other Expenses" remainder.
        """
        if month_data.empty:
            return month_data
        yearly_rules = YearlyBudgetService(self.db).get_year_rules(year)
        if yearly_rules.empty:
            return month_data
        cat_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        mask = pd.Series(False, index=month_data.index)
        for _, rule in yearly_rules.iterrows():
            in_cat = month_data[cat_col] == rule[CATEGORY]
            if self._is_all_tags(rule[TAGS]):
                mask |= in_cat
            else:
                mask |= in_cat & month_data[tag_col].isin(rule[TAGS])
        return month_data.loc[~mask]

    def get_monthly_budget_view(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> Optional[list[dict]]:
        """
        Compute budget rule usage view for a given month.

        Matches transactions to budget rules and calculates actual spend per rule.
        Project-category transactions and pending-refund transactions are excluded.
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
        budget_rules = self.get_all_rules()
        expenses = self.get_filtered_expenses(
            exclude_pending_refunds=True,
            include_split_parents=include_split_parents,
        )

        if not expenses.empty:
            expenses = self._apply_month_overrides(expenses)
            month_data = expenses.loc[
                (expenses["budget_year"] == year)
                & (expenses["budget_month"] == month)
            ]
            month_data = self._exclude_yearly_claimed(month_data, year)
        else:
            month_data = expenses

        rules = budget_rules[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]
        if rules.empty:
            return None

        view = []

        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            total = month_data[TransactionsTableFields.AMOUNT.value].sum() * -1
            view.append(
                {
                    "rule": total_rule.iloc[0].to_dict(),
                    "current_amount": total,
                    "data": month_data.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": False,
                }
            )
            rules = rules.loc[~rules.index.isin(total_rule.index)]
        remaining_data = month_data.copy()
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            cat_data = remaining_data[
                remaining_data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]
            ]

            is_all_tags = [t.lower() for t in tags] == [ALL_TAGS.lower()]
            if not is_all_tags:
                cat_data = cat_data[
                    cat_data[TransactionsTableFields.TAG.value].isin(tags)
                ]

            amt = cat_data[TransactionsTableFields.AMOUNT.value].sum() * -1
            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": amt,
                    "data": cat_data.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

            remaining_data = remaining_data.loc[
                ~remaining_data.index.isin(cat_data.index)
            ]

        if not remaining_data.empty and not rules.empty and not total_rule.empty:
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
                    "current_amount": remaining_data[
                        TransactionsTableFields.AMOUNT.value
                    ].sum()
                    * -1,
                    "data": remaining_data.to_dict(orient="records"),
                    "allow_edit": False,
                    "allow_delete": False,
                }
            )

        return view

    def get_monthly_project_transactions(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> Optional[pd.DataFrame]:
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
        budget_rules = self.budget_repository.read_all()
        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )

        if all_data.empty:
            return None

        # Only expenses (exclude income, liabilities, etc.)
        expenses = all_data.loc[
            ~all_data[TransactionsTableFields.CATEGORY.value].isin(
                EXPENSE_EXCLUDED_CATEGORIES
            )
        ].copy()
        expenses[TransactionsTableFields.DATE.value] = pd.to_datetime(
            expenses[TransactionsTableFields.DATE.value]
        )

        # Get project categories
        project_categories = budget_rules[
            budget_rules[YEAR].isnull() & budget_rules[MONTH].isnull()
        ][CATEGORY].unique()

        if len(project_categories) == 0:
            return None

        # Filter for project transactions in the specified month
        project_transactions = expenses.loc[
            (expenses[TransactionsTableFields.DATE.value].dt.year == year)
            & (expenses[TransactionsTableFields.DATE.value].dt.month == month)
            & expenses[TransactionsTableFields.CATEGORY.value].isin(project_categories)
        ]

        return project_transactions if not project_transactions.empty else None

    def get_monthly_project_spending_summary(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict:
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

        cat_col = TransactionsTableFields.CATEGORY.value
        amount_col = TransactionsTableFields.AMOUNT.value

        projects_summary = []
        for project_name, group in project_txns.groupby(cat_col):
            # Handle NaNs for JSON serialization
            group_processed = group.where(pd.notnull(group), None)
            total_spent = group_processed[amount_col].sum() * -1
            projects_summary.append(
                {
                    "category": str(project_name),
                    "spent": float(total_spent),
                    "transactions": group_processed.to_dict(orient="records"),
                }
            )

        return {
            "projects": projects_summary,
            "total_spent": float(project_txns[amount_col].sum() * -1),
        }

    def get_alerts(
        self,
        year: int,
        month: int,
        warning_threshold: float = 0.8,
    ) -> list[dict]:
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
        view = self.get_monthly_budget_view(year, month)
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
