"""
Budget service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for budget rule operations.
"""

import calendar
import threading
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import CREDIT_CARDS
from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.categories import INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY, IncomeCategories
from backend.constants.tables import TransactionsTableFields
from backend.errors import EntityNotFoundException
from backend.repositories.budget_repository import BudgetRepository
from backend.services.budget_month_override_service import BudgetMonthOverrideService
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.tagging_service import CategoriesTagsService
from backend.services.transactions_service import TransactionsService


# Serializes the auto-fill of a month's budget rules across concurrent
# requests. FastAPI runs the (synchronous) budget-analysis handlers in its
# worker threadpool, and the budget page fires the active month's request
# alongside prefetches for adjacent months. Auto-fill is a read-modify-write
# (read "month is empty" -> copy the source month's rules in), so without a
# guard each racing request reads its own snapshot as empty and copies the
# source month, duplicating every rule. A single-process lock is sufficient:
# the app runs one uvicorn process, and the desktop bundle likewise.
_auto_fill_lock = threading.Lock()


def _today() -> date:
    """Return today's date. Indirection point so tests can monkeypatch the clock."""
    return date.today()


class BudgetService:
    """
    Service for budget rule business logic.

    Provides methods for creating, retrieving, validating, and
    analyzing budget rules.
    """

    def __init__(self, db: Session):
        """
        Initialize the budget service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.budget_repository = BudgetRepository(db)
        self.categories_tags_service = CategoriesTagsService(db)
        self.transactions_service = TransactionsService(db)
        self.pending_refunds_service = PendingRefundsService(db)
        self.month_override_service = BudgetMonthOverrideService(db)

    def get_all_rules(self) -> pd.DataFrame:
        """
        Get all budget rules with tags parsed from semicolon strings to lists.

        Returns
        -------
        pd.DataFrame
            All budget rules. The ``tags`` column is a list of strings
            instead of the raw semicolon-separated string stored in the DB.
        """
        rules = self.budget_repository.read_all()
        if not rules.empty:
            rules[TAGS] = rules[TAGS].apply(
                lambda x: x.split(";") if isinstance(x, str) else []
            )
        return rules

    def add_rule(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        month: Optional[int] = None,
        year: Optional[int] = None,
        period_type: Optional[str] = None,
    ) -> None:
        """
        Add a new budget rule, converting tags to semicolon-separated storage format.

        ``period_type`` is forwarded to the repository, which derives it from
        ``(year, month)`` when ``None``.

        Parameters
        ----------
        name : str
            Human-readable label for the rule.
        amount : float
            Budget limit amount (must be positive).
        category : str
            Category the rule applies to, or ``"Total Budget"`` for an overall cap.
        tags : str or list[str]
            One or more tags the rule covers. Lists are joined with ``;``.
        month : int, optional
            Calendar month (1–12). ``None`` for project budgets.
        year : int, optional
            Calendar year. ``None`` for project budgets.
        period_type : str, optional
            One of ``"monthly"``, ``"yearly"``, or ``"project"``. When
            ``None``, the repository derives it from ``(year, month)``.
        """
        tags_str = ";".join(tags) if isinstance(tags, list) else tags
        self.budget_repository.add(name, amount, category, tags_str, month, year, period_type)

    def update_rule(self, id_: int, **fields):
        """
        Update a budget rule with validation and tag list-to-string conversion.

        Parameters
        ----------
        id_ : int
            ID of the budget rule to update.
        **fields
            Keyword arguments for fields to update. Allowed keys are
            ``name``, ``amount``, ``category``, and ``tags``.
            If ``tags`` is a list, it is joined with ``;`` before saving.

        Raises
        ------
        AssertionError
            If any key in ``fields`` is not one of the allowed field names.
        """
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        assert all(k in valid_fields for k in fields), (
            f"Invalid fields for update. Valid fields: {valid_fields}"
        )

        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])

        self.budget_repository.update(id_, **fields)

    def delete_rule(self, id_: int) -> None:
        """
        Delete a budget rule by ID.

        Parameters
        ----------
        id_ : int
            ID of the budget rule to delete.
        """
        self.budget_repository.delete(id_)

    def _rules_of_type_for(
        self, category: str, year: int, period_type: str
    ) -> pd.DataFrame:
        """All rules of ``period_type`` for a given category and year (tags as lists).

        Reads through the base ``BudgetService.get_all_rules`` explicitly
        (bypassing any subclass override) since ``period_type`` here is a
        caller-supplied filter that may name a different period than the
        calling service's own kind (e.g. a ``YearlyBudgetService`` checking
        for monthly conflicts). A polymorphic ``self.get_all_rules()`` would
        already be pre-filtered to the calling subclass's period type and
        could never see rules of any other kind.
        """
        rules = BudgetService.get_all_rules(self)
        if rules.empty:
            return rules
        return rules.loc[
            (rules[PERIOD_TYPE] == period_type)
            & (rules[YEAR] == year)
            & (rules[CATEGORY] == category)
        ]

    @staticmethod
    def _is_all_tags(tags: list[str]) -> bool:
        """True when a tag list is the all-tags sentinel (case-insensitive)."""
        return [t.lower() for t in tags] == [ALL_TAGS.lower()]

    def find_conflicting_tags(
        self,
        category: str,
        tags: list[str],
        year: int,
        other_period_type: str,
        *,
        exclude_rule_id: int | None = None,
    ) -> list[str]:
        """Return incoming tags that collide with existing ``other_period_type`` rules.

        Two rules conflict when they share ``category`` and ``year`` and at least
        one tag. An ``all_tags`` sentinel on either side claims the whole category,
        so every incoming (non-sentinel) tag conflicts.

        Parameters
        ----------
        category : str
            Category of the incoming rule.
        tags : list[str]
            Incoming tag list (may be the ``all_tags`` sentinel).
        year : int
            Calendar year the incoming rule applies to.
        other_period_type : str
            The budget kind to check against (e.g. ``"yearly"`` when validating a
            monthly rule).
        exclude_rule_id : int, optional
            A rule id to ignore (the rule being edited).

        Returns
        -------
        list[str]
            Sorted conflicting tag names. Empty when there is no conflict. When
            the incoming rule is itself ``all_tags`` and any other rule exists in
            the category+year, returns ``["all_tags"]`` to signal a whole-category
            conflict.
        """
        others = self._rules_of_type_for(category, year, other_period_type)
        if exclude_rule_id is not None and not others.empty:
            others = others.loc[others[ID] != exclude_rule_id]
        if others.empty:
            return []

        if self._is_all_tags(tags):
            # Incoming claims the whole category; any existing rule collides.
            return [ALL_TAGS]

        conflicts: set[str] = set()
        for _, other in others.iterrows():
            other_tags = other[TAGS]
            if self._is_all_tags(other_tags):
                conflicts.update(tags)
            else:
                conflicts.update(set(tags) & set(other_tags))
        return sorted(conflicts)

    def is_category_project_owned(self, category: str) -> bool:
        """True if any project rule uses ``category``.

        Reads through the unfiltered base ``get_all_rules`` so it works from any
        subclass.
        """
        rules = BudgetService.get_all_rules(self)
        if rules.empty:
            return False
        return not rules.loc[
            (rules[PERIOD_TYPE] == PERIOD_PROJECT) & (rules[CATEGORY] == category)
        ].empty

    def category_used_by_monthly_or_yearly(self, category: str) -> bool:
        """True if any monthly or yearly rule uses ``category`` (excluding the
        ``Total Budget`` cap category, which is not a real category)."""
        if category == TOTAL_BUDGET:
            return False
        rules = BudgetService.get_all_rules(self)
        if rules.empty:
            return False
        return not rules.loc[
            (rules[PERIOD_TYPE].isin([PERIOD_MONTHLY, PERIOD_YEARLY]))
            & (rules[CATEGORY] == category)
            & (rules[CATEGORY] != TOTAL_BUDGET)
        ].empty

    def find_category_overlaps(self) -> list[dict]:
        """Categories that are BOTH project-owned and budget-used.

        Returns
        -------
        list[dict]
            One entry per overlapping category:
            ``{"category": str, "kinds": [<"monthly"|"yearly">, ...]}`` — the
            non-project kinds that collide, sorted. Empty when there is no
            overlap.
        """
        rules = BudgetService.get_all_rules(self)
        if rules.empty:
            return []
        project_cats = set(
            rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT, CATEGORY].dropna()
        )
        overlaps = []
        for cat in sorted(project_cats):
            kinds = sorted(
                {
                    pt
                    for pt in rules.loc[
                        (rules[CATEGORY] == cat)
                        & (rules[PERIOD_TYPE].isin([PERIOD_MONTHLY, PERIOD_YEARLY])),
                        PERIOD_TYPE,
                    ]
                }
            )
            if kinds:
                overlaps.append({"category": cat, "kinds": kinds})
        return overlaps

    def strip_conflicting_tags(
        self,
        category: str,
        tags: list[str],
        year: int,
        other_period_type: str,
    ) -> tuple[list[str], list[str]]:
        """Split ``tags`` into (kept, skipped) for auto-fill/carry-forward.

        Skipped tags are those that conflict with ``other_period_type`` rules for
        the same category+year. If the incoming rule is ``all_tags`` and conflicts,
        all-tags is treated as fully skipped (returns ``([], ["all_tags"])``).
        """
        conflicts = set(
            self.find_conflicting_tags(category, tags, year, other_period_type)
        )
        if not conflicts:
            return list(tags), []
        if self._is_all_tags(tags):
            return [], [ALL_TAGS]
        kept = [t for t in tags if t not in conflicts]
        skipped = [t for t in tags if t in conflicts]
        return kept, skipped

    @staticmethod
    def validate_rule_inputs(
        budget_rules: pd.DataFrame,
        name: str,
        category: str,
        tags: list[str],
        amount: float,
        year: int | None,
        month: int | None,
        id_: int | None,
    ) -> tuple[bool, str]:
        """
        Validate budget rule inputs before creating or updating.

        Checks include: name uniqueness, non-empty fields, positive amount,
        and that adding/changing the rule does not exceed the total budget cap.
        For project rules (month/year are ``None``), validates against the
        project total instead of the monthly total.

        Parameters
        ----------
        budget_rules : pd.DataFrame
            All existing budget rules (from ``get_all_rules``).
        name : str
            Proposed rule name.
        category : str
            Category the rule applies to.
        tags : list[str]
            Tags the rule covers.
        amount : float
            Proposed budget amount.
        year : int or None
            Rule year; ``None`` for project rules.
        month : int or None
            Rule month; ``None`` for project rules.
        id_ : int or None
            Existing rule ID when updating, ``None`` when creating.

        Returns
        -------
        tuple[bool, str]
            ``(True, "")`` if valid, or ``(False, error_message)`` if not.
        """
        if id_ is not None:
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            if (
                rule[NAME] == name
                and rule[AMOUNT] == amount
                and rule[CATEGORY] == category
                and rule[TAGS] == tags
            ):
                return True, ""

        # Unique name check
        if pd.isnull(year) and pd.isnull(month):
            duplicate = budget_rules.loc[
                (budget_rules[YEAR].isnull())
                & (budget_rules[MONTH].isnull())
                & (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return False, f"A project rule with the name '{name}' already exists."
        else:
            duplicate = budget_rules.loc[
                (budget_rules[YEAR] == year)
                & (budget_rules[MONTH] == month)
                & (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return (
                    False,
                    f"A rule with the name '{name}' already exists for this month.",
                )

        if name == "":
            return False, "Please enter a name"
        if category is None:
            return False, "Please select a category"
        if not tags:
            return False, "Please select at least one tag"
        if amount <= 0:
            return False, "Amount must be a positive number"

        if pd.isnull(year) and pd.isnull(month):
            # When editing an existing rule we look it up to know its current
            # tags/amount; when creating (id_ is None) there is no existing row,
            # so fall back to the incoming tags and a zero current amount.
            if id_ is not None:
                rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
                rule_tags = rule[TAGS]
                existing_amount = rule[AMOUNT]
            else:
                rule_tags = tags
                existing_amount = 0
            budget_rules = budget_rules.loc[
                (budget_rules[YEAR].isnull())
                & (budget_rules[MONTH].isnull())
                & (budget_rules[CATEGORY] == category)
            ]
            total_rules_amount = budget_rules.loc[
                ~budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT
            ].sum()
            if rule_tags == [ALL_TAGS]:
                if amount < total_rules_amount:
                    return (
                        False,
                        "The total budget must be greater than the sum of all other rules",
                    )
            else:
                total_budget = budget_rules.loc[
                    budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT
                ].values[0]
                new_total_rules_amount = total_rules_amount - existing_amount + amount
                if new_total_rules_amount > total_budget:
                    return False, "The total budget is exceeded"
            return True, ""

        budget_rules = budget_rules.loc[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]
        total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][
            AMOUNT
        ].sum()

        if category == TOTAL_BUDGET:
            if amount < total_rules_amount:
                return (
                    False,
                    "The total budget must be greater than the sum of all other rules",
                )
            return True, ""

        if id_ is not None:
            total_rules_amount -= budget_rules.loc[budget_rules[ID] == id_][
                AMOUNT
            ].values[0]
        total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][
            AMOUNT
        ].values[0]
        new_total_rules_amount = total_rules_amount + amount
        if new_total_rules_amount > total_budget:
            return False, "The total budget is exceeded"

        if tags == [ALL_TAGS]:
            condition = budget_rules[CATEGORY] == category
            if id_ is not None:
                condition &= budget_rules[ID] != id_
            if not budget_rules.loc[condition].empty:
                return (
                    False,
                    f"Cannot have {ALL_TAGS} for a category with existing specific tag rules",
                )

        return True, ""

    def get_filtered_expenses(
        self,
        exclude_pending_refunds: bool = True,
        include_split_parents: bool = False,
    ) -> pd.DataFrame:
        """
        Get expense transactions with budget-style filtering applied.

        Loads all transactions (split-aware), then excludes non-expense
        categories, project categories, and optionally pending refund
        transactions. Split parent rows are excluded from the result.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            When ``True``, excludes transactions marked as pending refunds.
            Default is ``True``.
        include_split_parents : bool, optional
            When ``True``, include parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        pd.DataFrame
            Filtered expense transactions with parsed dates. Amounts are
            negative (raw convention). The caller should negate to get
            positive expense values.
        """
        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )

        if all_data.empty:
            return all_data

        # Filter to expense categories
        expenses = all_data.loc[
            ~all_data[TransactionsTableFields.CATEGORY.value].isin(
                [INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY, CREDIT_CARDS, *IncomeCategories._value2member_map_.keys()]
            )
        ].copy()
        expenses[TransactionsTableFields.DATE.value] = pd.to_datetime(
            expenses[TransactionsTableFields.DATE.value]
        )

        # Exclude project categories
        projects = ProjectBudgetService(self.db).get_all_projects_names()
        if projects:
            expenses = expenses.loc[
                ~expenses[TransactionsTableFields.CATEGORY.value].isin(projects)
            ]

        # Optionally exclude pending refunds
        if exclude_pending_refunds:
            pending_refs = self.pending_refunds_service.get_active_pending_identifiers()
            tx_ids = pending_refs["transaction_ids"]
            split_ids = pending_refs["split_ids"]

            expenses = expenses[
                ~expenses[TransactionsTableFields.UNIQUE_ID.value].isin(tx_ids)
            ]
            if TransactionsTableFields.SPLIT_ID.value in expenses.columns:
                expenses = expenses[
                    ~expenses[TransactionsTableFields.SPLIT_ID.value].isin(split_ids)
                ]

        # Exclude split_parent transactions from amounts
        if "type" in expenses.columns:
            expenses = expenses[expenses["type"] != "split_parent"]

        return expenses


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

        skipped: list[str] = []
        for _, rule in rules_to_copy.iterrows():
            tags = rule[TAGS]
            # Only run the conflict check when there are tags to check — a
            # rule with no tags (e.g. Total Budget, or a legacy rule with
            # tags=None) always gets copied as-is, matching prior behavior.
            if rule[CATEGORY] != TOTAL_BUDGET and tags:
                kept, dropped = self.strip_conflicting_tags(
                    rule[CATEGORY], tags, year, PERIOD_YEARLY
                )
            else:
                kept, dropped = tags, []
            skipped.extend(dropped)
            if tags and not kept:
                continue
            self.add_rule(
                name=rule[NAME],
                amount=rule[AMOUNT],
                category=rule[CATEGORY],
                tags=kept,
                month=month,
                year=year,
            )
        self._last_copy_skipped = skipped

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
                for _, rule in source_rules.iterrows():
                    tags = rule[TAGS]
                    # Only run the conflict check when there are tags to
                    # check — a rule with no tags always gets copied as-is,
                    # matching prior behavior.
                    if rule[CATEGORY] != TOTAL_BUDGET and tags:
                        kept, dropped = self.strip_conflicting_tags(
                            rule[CATEGORY], tags, y, PERIOD_YEARLY
                        )
                    else:
                        kept, dropped = tags, []
                    skipped.extend(dropped)
                    if tags and not kept:
                        continue
                    self.add_rule(
                        name=rule[NAME],
                        amount=rule[AMOUNT],
                        category=rule[CATEGORY],
                        tags=kept,
                        month=m,
                        year=y,
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
                [INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY, CREDIT_CARDS, *IncomeCategories._value2member_map_.keys()]
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


class ProjectBudgetService(BudgetService):
    """Service for managing project-based budget rules."""

    def get_all_rules(self) -> pd.DataFrame:
        """Get all project budget rules (period_type == 'project')."""
        rules = super().get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT].drop(
            columns=[YEAR, MONTH]
        )

    def get_rules_for_project(self, category: str) -> pd.DataFrame:
        """
        Get all budget rules for a specific project category.

        Parameters
        ----------
        category : str
            Project category name.

        Returns
        -------
        pd.DataFrame
            Budget rules for the project.

        Raises
        ------
        ValueError
            If no rules exist for the given project category.
        """
        rules = self.get_all_rules()
        if rules.empty:
            raise ValueError(f"Project {category} not found")

        rules = rules.loc[rules[CATEGORY] == category]
        return rules

    def create_project(self, category: str, total_budget: float) -> None:
        """
        Create a new project budget with a total rule and per-tag sub-rules.

        Adds a ``Total Budget`` rule for the category and individual zero-amount
        rules for every tag in the category.

        Parameters
        ----------
        category : str
            Project category name (must already exist in categories config).
        total_budget : float
            Overall spending limit for the project.

        Raises
        ------
        ValueError
            If ``category`` already has a monthly or yearly budget rule. A
            category can't be in both a project and a monthly/yearly budget.
        """
        if self.category_used_by_monthly_or_yearly(category):
            raise ValueError(
                f"The '{category}' category is already used by a monthly or "
                f"yearly budget. A category can't be in both a project and a "
                f"monthly/yearly budget."
            )

        self.add_rule(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=category,
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )

        tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        tags = tags[category]
        for tag in tags:
            self.add_rule(
                name=tag, amount=0, category=category, tags=[tag], month=None, year=None
            )

    def update_project(self, category: str, total_budget: float) -> None:
        """
        Update the total budget amount for an existing project.

        Parameters
        ----------
        category : str
            Project category name.
        total_budget : float
            New overall spending limit for the project.
        """
        rules = self.get_rules_for_project(category)
        total_rule = rules.loc[rules[TAGS].apply(lambda x: x == [ALL_TAGS])]
        if total_rule.empty:
            raise EntityNotFoundException(
                f"No total budget rule found for project '{category}'"
            )
        rule_id = int(total_rule.iloc[0][ID])
        self.update_rule(rule_id, amount=total_budget)

    def delete_project(self, category: str) -> None:
        """
        Delete all budget rules for a project category.

        Parameters
        ----------
        category : str
            Project category name whose rules should be deleted.
        """
        self.budget_repository.delete_by_category(category)

    def delete_project_tag_rule(self, category: str, tag: str) -> None:
        """
        Delete a specific tag rule from a project.

        Parameters
        ----------
        category : str
            Project category name.
        tag : str
            Tag whose budget rule should be deleted.
        """
        self.budget_repository.delete_by_category_and_tags(category, tag)

    def get_project_transactions(
        self, project: str, include_split_parents: bool = False
    ) -> pd.DataFrame:
        """
        Get all transactions categorised under a project category.

        Parameters
        ----------
        project : str
            Project category name.
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        pd.DataFrame
            Transactions where category equals ``project``.
        """
        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )
        return all_data.loc[all_data[TransactionsTableFields.CATEGORY.value] == project]

    def get_all_projects_names(self) -> list[str]:
        """
        Get the names of all project categories that have budget rules.

        Returns
        -------
        list[str]
            Unique category names from all project budget rules.
        """
        rules = self.get_all_rules()
        return rules[CATEGORY].unique().tolist()

    def get_available_categories_for_new_project(self) -> list[str]:
        """
        Get categories that can be used for a new project (not already tracked).

        Returns
        -------
        list[str]
            Category names from the categories config that are not already
            used as project budget categories, and do not already have a
            monthly or yearly budget rule.
        """
        current_projects = self.get_all_projects_names()
        new_possible_projects = [
            cat
            for cat in self.categories_tags_service.get_categories_and_tags(
                copy=True
            ).keys()
            if cat not in current_projects
            and not self.category_used_by_monthly_or_yearly(cat)
        ]
        return new_possible_projects

    def get_project_budget_view(
        self, project: str, include_split_parents: bool = False
    ) -> dict:
        """
        Get project details including rules and transactions.

        Matches project transactions to budget rules. Any transactions whose
        tag does not match an existing rule automatically trigger creation of
        a new zero-budget rule for that tag (side-effect for new tags).

        Parameters
        ----------
        project : str
            Project category name.
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``name`` – project category name.
            - ``rules`` – list of rule view dicts (same shape as ``get_monthly_budget_view``).
            - ``total_spent`` – total amount spent on the project.
        """
        rules = self.get_rules_for_project(project)
        transactions = self.get_project_transactions(project, include_split_parents)

        view = []

        # Total Project Rule
        total_rule = pd.DataFrame()
        if not rules.empty:
            # Find where tags == [ALL_TAGS] (handle case sensitivity)
            total_rule = rules[
                rules[TAGS].apply(
                    lambda x: [t.lower() for t in x] == [ALL_TAGS.lower()]
                )
            ]

        # Ensure transactions is JSON serializable (handle NaNs)
        transactions_processed = transactions.where(pd.notnull(transactions), None)

        # Exclude split_parent transactions from total calculation
        if "type" in transactions.columns:
            non_parent_txns = transactions[transactions["type"] != "split_parent"]
        else:
            non_parent_txns = transactions
        total_spent = non_parent_txns[TransactionsTableFields.AMOUNT.value].sum() * -1

        if not total_rule.empty:
            view.append(
                {
                    "rule": total_rule.iloc[0].to_dict(),
                    "current_amount": total_spent,
                    "data": transactions_processed.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": False,
                }
            )
            rules = rules.drop(total_rule.index)

        # Track transactions that have been matched to a rule
        matched_txns_indices = set()

        # Per tag rules
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            # Filter transactions for these tags using original DataFrame for calculation
            tag_txns_orig = transactions[
                transactions[TransactionsTableFields.TAG.value].isin(tags)
            ]

            # Record indices of matched transactions
            matched_txns_indices.update(tag_txns_orig.index)

            # Exclude split_parent transactions from spent calculation
            if "type" in tag_txns_orig.columns:
                tag_txns_for_calc = tag_txns_orig[
                    tag_txns_orig["type"] != "split_parent"
                ]
            else:
                tag_txns_for_calc = tag_txns_orig
            spent = tag_txns_for_calc[TransactionsTableFields.AMOUNT.value].sum() * -1

            # Filter processed transactions for display
            tag_txns_display = transactions_processed[
                transactions_processed[TransactionsTableFields.TAG.value].isin(tags)
            ]

            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": spent,
                    "data": tag_txns_display.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

        # Handle unmatched transactions ("Other" or random tags)
        unmatched_txns = transactions.loc[
            ~transactions.index.isin(matched_txns_indices)
        ]

        if not unmatched_txns.empty:
            for tag, group in unmatched_txns.groupby(TransactionsTableFields.TAG.value):
                self.add_rule(
                    name=tag,
                    amount=0,
                    category=project,
                    tags=[tag],
                    month=None,
                    year=None,
                )

                if "type" in group.columns:
                    group_for_calc = group[group["type"] != "split_parent"]
                else:
                    group_for_calc = group

                spent = group_for_calc[TransactionsTableFields.AMOUNT.value].sum() * -1

                group_display = transactions_processed.loc[group.index]

                new_rule_df = self.budget_repository.read_all()
                new_rule = new_rule_df[
                    (new_rule_df[CATEGORY] == project)
                    & (new_rule_df[YEAR].isnull())
                    & (new_rule_df[MONTH].isnull())
                    & (new_rule_df[NAME] == tag)
                ]

                rule_dict = {}
                if not new_rule.empty:
                    r = new_rule.iloc[0]
                    rule_dict = r.to_dict()
                    if isinstance(rule_dict[TAGS], str):
                        rule_dict[TAGS] = rule_dict[TAGS].split(";")
                else:
                    rule_dict = {
                        NAME: tag,
                        AMOUNT: 0,
                        CATEGORY: project,
                        TAGS: [tag],
                        ID: 0,
                    }

                view.append(
                    {
                        "rule": rule_dict,
                        "current_amount": spent,
                        "data": group_display.to_dict(orient="records"),
                        "allow_edit": True,
                        "allow_delete": True,
                    }
                )

        return {"name": project, "rules": view, "total_spent": total_spent}


class YearlyBudgetService(BudgetService):
    """Service for managing yearly budget rules.

    A yearly budget is a flat list of independent ``(category, tags)`` rules for
    a calendar year. Spend accumulates over the whole year. There is no overall
    cap and no synthetic "Other Expenses" entry. Yearly rules are mutually
    exclusive with monthly rules on ``(category, tag)`` within the same year.
    """

    def get_all_rules(self) -> pd.DataFrame:
        """Get all yearly budget rules (period_type == 'yearly'), MONTH dropped."""
        rules = super().get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == PERIOD_YEARLY].drop(columns=[MONTH])

    def get_year_rules(self, year: int) -> pd.DataFrame:
        """Yearly rules scoped to a single calendar year."""
        rules = self.get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[YEAR] == year]

    def _validate(
        self,
        name: str,
        category: str,
        tags: list[str],
        amount: float,
        year: int,
        id_: int | None,
    ) -> None:
        """Validate a yearly rule; raise ``ValueError`` on failure.

        Checks: non-empty name/category/tags, positive amount, name uniqueness
        within the year, and mutual exclusion against monthly rules for the year.
        """
        if not name:
            raise ValueError("Please enter a name")
        if not category:
            raise ValueError("Please select a category")
        if not tags:
            raise ValueError("Please select at least one tag")
        if amount <= 0:
            raise ValueError("Amount must be a positive number")

        existing = self.get_year_rules(year)
        if not existing.empty:
            dupes = existing.loc[existing[NAME] == name]
            if id_ is not None:
                dupes = dupes.loc[dupes[ID] != id_]
            if not dupes.empty:
                raise ValueError(
                    f"A yearly rule with the name '{name}' already exists for {year}."
                )

        conflicts = self.find_conflicting_tags(
            category, tags, year, PERIOD_MONTHLY, exclude_rule_id=id_
        )
        if conflicts:
            joined = ", ".join(conflicts)
            raise ValueError(
                f"{joined} is already used by your monthly budget for {year}. "
                f"A tag can't be in both for the same year."
            )

        # A (category, tag) may not be covered by two yearly rules in the same
        # year. Unlike monthly rules (bounded by the Total Budget cap), yearly
        # rules have no overall cap, so a shared tag would double-count in the
        # roll-up's total_spent/remaining/health.
        yearly_conflicts = self.find_conflicting_tags(
            category, tags, year, PERIOD_YEARLY, exclude_rule_id=id_
        )
        if yearly_conflicts:
            if yearly_conflicts == [ALL_TAGS]:
                raise ValueError(
                    f"Another yearly rule already covers the '{category}' "
                    f"category for {year}."
                )
            joined = ", ".join(yearly_conflicts)
            raise ValueError(
                f"{joined} is already used by another yearly rule for {year}. "
                f"A tag can't be in two yearly rules for the same year."
            )

        if self.is_category_project_owned(category):
            raise ValueError(
                f"The '{category}' category belongs to a project budget. "
                f"A yearly rule can't target a project category."
            )

    def create_rule(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        year: int,
    ) -> None:
        """Create a yearly rule after validation. Raises ``ValueError`` if invalid."""
        parsed_tags = tags.split(";") if isinstance(tags, str) else list(tags)
        self._validate(name, category, parsed_tags, amount, year, None)
        self.add_rule(name, amount, category, parsed_tags, month=None, year=year,
                      period_type=PERIOD_YEARLY)

    def update_rule(self, id_: int, **fields):
        """Update a yearly rule with validation of any category/tags/name/amount change.

        Allowed fields: ``name``, ``amount``, ``category``, ``tags``. The rule's
        ``year`` is immutable via this method.
        """
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        assert all(k in valid_fields for k in fields), (
            f"Invalid fields for update. Valid fields: {valid_fields}"
        )
        current = self.get_all_rules()
        row = current.loc[current[ID] == id_]
        if row.empty:
            raise ValueError(f"No yearly rule found with ID {id_}.")
        row = row.iloc[0]
        year = int(row[YEAR])
        name = fields.get(NAME, row[NAME])
        amount = fields.get(AMOUNT, row[AMOUNT])
        category = fields.get(CATEGORY, row[CATEGORY])
        tags = fields.get(TAGS, row[TAGS])
        parsed_tags = tags.split(";") if isinstance(tags, str) else list(tags)
        self._validate(name, category, parsed_tags, amount, year, id_)

        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])
        self.budget_repository.update(id_, **fields)

    def get_yearly_budget_view(
        self, year: int, include_split_parents: bool = False
    ) -> Optional[list[dict]]:
        """Compute spend-vs-limit per yearly rule for a calendar year.

        Returns ``None`` when the year has no yearly rules. Otherwise a flat list
        of ``{rule, current_amount, data, allow_edit, allow_delete}`` — no total
        rule, no "Other Expenses" remainder.
        """
        rules = self.get_year_rules(year)
        if rules.empty:
            return None

        expenses = self.get_filtered_expenses(
            exclude_pending_refunds=True, include_split_parents=include_split_parents
        )
        if not expenses.empty:
            year_data = expenses.loc[
                pd.to_datetime(expenses[TransactionsTableFields.DATE.value]).dt.year == year
            ]
        else:
            year_data = expenses

        view = []
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            if year_data.empty:
                cat_data = year_data
            else:
                cat_data = year_data[
                    year_data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]
                ]
                if not self._is_all_tags(tags):
                    cat_data = cat_data[
                        cat_data[TransactionsTableFields.TAG.value].isin(tags)
                    ]
            amt = (
                cat_data[TransactionsTableFields.AMOUNT.value].sum() * -1
                if not cat_data.empty
                else 0.0
            )
            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": amt,
                    "data": cat_data.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )
        return view

    def get_year_summary(self, year: int) -> dict:
        """Computed, display-only roll-up for the year header.

        Returns
        -------
        dict
            ``total_allocated``, ``total_spent``, ``remaining``, ``on_track``
            (count of rules at/under budget), ``over`` (count over budget), and
            ``biggest_overspend`` (``{"name", "percentage"}`` or ``None``).
        """
        view = self.get_yearly_budget_view(year) or []
        total_allocated = sum(float(e["rule"].get(AMOUNT) or 0) for e in view)
        total_spent = sum(float(e["current_amount"] or 0) for e in view)
        on_track = 0
        over = 0
        biggest = None
        for e in view:
            amount = float(e["rule"].get(AMOUNT) or 0)
            spent = float(e["current_amount"] or 0)
            pct = spent / amount if amount > 0 else 0.0
            if amount > 0 and spent > amount:
                over += 1
                if biggest is None or pct > biggest["percentage"]:
                    biggest = {"name": str(e["rule"].get(NAME) or ""), "percentage": pct}
            else:
                on_track += 1
        return {
            "total_allocated": total_allocated,
            "total_spent": total_spent,
            "remaining": total_allocated - total_spent,
            "on_track": on_track,
            "over": over,
            "biggest_overspend": biggest,
        }

    def get_alerts(self, year: int, warning_threshold: float = 0.8) -> list[dict]:
        """Yearly rules whose spend reached the warning threshold.

        Mirrors ``MonthlyBudgetService.get_alerts`` — ``percentage = spent/amount``;
        ``critical`` at ≥ 1.0, ``warning`` in ``[threshold, 1.0)``. There is no
        Total Budget / Other Expenses row to skip.
        """
        view = self.get_yearly_budget_view(year)
        if view is None:
            return []
        alerts = []
        for entry in view:
            rule = entry["rule"]
            amount = float(rule.get(AMOUNT) or 0)
            if amount <= 0:
                continue
            spent = float(entry.get("current_amount") or 0)
            percentage = spent / amount
            if percentage < warning_threshold:
                continue
            alerts.append(
                {
                    "rule_id": int(rule[ID]),
                    "name": str(rule.get(NAME) or ""),
                    "category": str(rule.get(CATEGORY) or ""),
                    "tags": list(rule.get(TAGS) or []),
                    "amount": amount,
                    "spent": spent,
                    "percentage": percentage,
                    "severity": "critical" if percentage >= 1.0 else "warning",
                }
            )
        alerts.sort(key=lambda a: a["percentage"], reverse=True)
        return alerts

    def auto_carry_forward(self, year: int) -> Optional[dict]:
        """Copy the latest prior year's yearly rules into an empty ``year``.

        Only runs for the current or a future year (never rewrites history) and
        only when ``year`` has no yearly rules yet. Tags that conflict with
        monthly rules for ``year`` are stripped; a rule left with no tags is
        skipped entirely.

        Returns
        -------
        dict or None
            ``{"copied_from": <int year>, "skipped": [<tag>, ...]}`` when rules
            were copied, else ``None``.
        """
        if year < _today().year:
            return None
        with _auto_fill_lock:
            self.db.rollback()
            if not self.get_year_rules(year).empty:
                return None
            all_rules = self.get_all_rules()
            if all_rules.empty:
                return None
            prior = all_rules.loc[all_rules[YEAR] < year]
            if prior.empty:
                return None
            source_year = int(prior[YEAR].max())
            source_rules = all_rules.loc[all_rules[YEAR] == source_year]

            skipped: list[str] = []
            for _, rule in source_rules.iterrows():
                kept, dropped = self.strip_conflicting_tags(
                    rule[CATEGORY], rule[TAGS], year, PERIOD_MONTHLY
                )
                skipped.extend(dropped)
                if not kept:
                    continue
                self.add_rule(
                    name=rule[NAME], amount=rule[AMOUNT], category=rule[CATEGORY],
                    tags=kept, month=None, year=year, period_type=PERIOD_YEARLY,
                )
            return {"copied_from": source_year, "skipped": skipped}

    def force_copy_from_prior_year(self, year: int) -> Optional[dict]:
        """Force-copy the latest prior year's yearly rules into ``year``.

        This is the explicit user-triggered "Copy from previous year" action
        (the ``/yearly/{year}/copy`` route), distinct from
        ``auto_carry_forward``: it does not gate on ``year`` being the
        current/future year, and it does not require ``year`` to already be
        empty — the user may be intentionally overwriting an existing year.

        To avoid data loss, the source year is resolved *first*. Only once a
        valid prior year with yearly rules is confirmed does this delete
        ``year``'s existing rules and copy the source rules forward. If no
        prior year has any yearly rules, nothing is deleted.

        Returns
        -------
        dict or None
            ``{"copied_from": <int year>, "skipped": [<tag>, ...]}`` when
            rules were copied. ``None`` when there is no prior year with
            yearly rules to copy from — in that case ``year``'s existing
            rules (if any) are left untouched.
        """
        all_rules = self.get_all_rules()
        if all_rules.empty:
            return None
        prior = all_rules.loc[all_rules[YEAR] < year]
        if prior.empty:
            return None
        source_year = int(prior[YEAR].max())
        source_rules = all_rules.loc[all_rules[YEAR] == source_year]

        with _auto_fill_lock:
            self.db.rollback()
            existing = self.get_year_rules(year)
            for _, r in existing.iterrows():
                self.delete_rule(int(r[ID]))

            skipped: list[str] = []
            for _, rule in source_rules.iterrows():
                kept, dropped = self.strip_conflicting_tags(
                    rule[CATEGORY], rule[TAGS], year, PERIOD_MONTHLY
                )
                skipped.extend(dropped)
                if not kept:
                    continue
                self.add_rule(
                    name=rule[NAME], amount=rule[AMOUNT], category=rule[CATEGORY],
                    tags=kept, month=None, year=year, period_type=PERIOD_YEARLY,
                )
            return {"copied_from": source_year, "skipped": sorted(set(skipped))}

    def get_yearly_analysis(
        self, year: int, include_split_parents: bool = False
    ) -> dict:
        """Bundle the yearly view, computed roll-up, alerts, and carry-forward report."""
        carried_from = None
        skipped_conflicts: list[str] = []
        if self.get_year_rules(year).empty and year >= _today().year:
            result = self.auto_carry_forward(year)
            if result is not None:
                carried_from = result["copied_from"]
                skipped_conflicts = result["skipped"]

        view = self.get_yearly_budget_view(year, include_split_parents)
        return {
            "rules": view if view else [],
            "summary": self.get_year_summary(year),
            "alerts": self.get_alerts(year),
            "carried_from": carried_from,
            "skipped_conflicts": sorted(set(skipped_conflicts)),
        }
