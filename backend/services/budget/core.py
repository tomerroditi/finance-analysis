"""
Core budget service with pure SQLAlchemy (no Streamlit dependencies).

This module provides the base ``BudgetService`` — rule CRUD, tag parsing,
validation, conflict helpers, and budget-style expense filtering shared by
the monthly, yearly, and project budget services.
"""

import threading
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

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
from backend.constants.tables import TransactionsTableFields
from backend.errors import ValidationException
from backend.services.transaction_classification import EXPENSE_EXCLUDED_CATEGORIES
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
        ValidationException
            If any key in ``fields`` is not one of the allowed field names.
        """
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        if not all(k in valid_fields for k in fields):
            raise ValidationException(
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

    def _copy_rules(
        self,
        source_rules: pd.DataFrame,
        *,
        conflict_period_type: str,
        target_year: int,
        target_month: Optional[int] = None,
        period_type: Optional[str] = None,
        total_budget_passthrough: bool = False,
    ) -> list[str]:
        """Copy ``source_rules`` into a target period, stripping conflicting tags.

        Shared engine behind ``copy_last_month_rules``, the auto-fill of empty
        months, ``auto_carry_forward``, and ``force_copy_from_prior_year``.
        Each source rule has its tags checked against existing
        ``conflict_period_type`` rules for ``target_year`` via
        ``strip_conflicting_tags``; conflicting tags are dropped and collected,
        and a rule left with no tags to copy is skipped entirely.

        Parameters
        ----------
        source_rules : pd.DataFrame
            Rules to copy (tags as lists, from ``get_all_rules``-style reads).
        conflict_period_type : str
            The budget kind to strip conflicts against (``"yearly"`` when
            copying monthly rules, ``"monthly"`` when copying yearly rules).
        target_year : int
            Year the copies are created in (also the conflict-check year).
        target_month : int, optional
            Month the copies are created in. ``None`` for yearly copies.
        period_type : str, optional
            Forwarded to ``add_rule`` (e.g. ``"yearly"``). When ``None``, the
            repository derives it from ``(target_year, target_month)``.
        total_budget_passthrough : bool, optional
            Monthly-copy semantics: when ``True``, a ``Total Budget`` rule or a
            rule with no tags (e.g. a legacy rule with ``tags=None``) bypasses
            the conflict check and is copied as-is, and only rules that *had*
            tags but lost them all are skipped. When ``False`` (yearly-copy
            semantics), every rule is conflict-checked and any rule with no
            kept tags is skipped.

        Returns
        -------
        list[str]
            Tag names dropped because of conflicts, in encounter order
            (may contain duplicates — callers dedupe as needed).
        """
        skipped: list[str] = []
        for _, rule in source_rules.iterrows():
            tags = rule[TAGS]
            if total_budget_passthrough and (rule[CATEGORY] == TOTAL_BUDGET or not tags):
                kept, dropped = tags, []
            else:
                kept, dropped = self.strip_conflicting_tags(
                    rule[CATEGORY], tags, target_year, conflict_period_type
                )
            skipped.extend(dropped)
            if total_budget_passthrough:
                if tags and not kept:
                    continue
            elif not kept:
                continue
            self.add_rule(
                name=rule[NAME],
                amount=rule[AMOUNT],
                category=rule[CATEGORY],
                tags=kept,
                month=target_month,
                year=target_year,
                period_type=period_type,
            )
        return skipped

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
                total_budget_rows = budget_rules.loc[
                    budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT
                ]
                if total_budget_rows.empty:
                    return (
                        False,
                        "Create the project's total budget rule before adding tag rules",
                    )
                total_budget = total_budget_rows.values[0]
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
        total_budget_rows = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][
            AMOUNT
        ]
        if total_budget_rows.empty:
            return (
                False,
                "Create a Total Budget rule for this month before adding category rules",
            )
        total_budget = total_budget_rows.values[0]
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
        # Local import: project.py subclasses this module's BudgetService.
        from backend.services.budget.project import ProjectBudgetService

        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )

        if all_data.empty:
            return all_data

        # Filter to expense categories
        expenses = all_data.loc[
            ~all_data[TransactionsTableFields.CATEGORY.value].isin(
                EXPENSE_EXCLUDED_CATEGORIES
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
