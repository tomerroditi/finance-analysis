"""
Core budget service.

This module provides the base ``BudgetService`` — rule reads and edits
(delegated to :class:`~backend.services.budget.rules.BudgetRuleStore`), the
period-copy engine, the claim ledger read, and budget-style expense filtering
shared by the monthly, yearly, and project budget services.
"""

import threading
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.budget import (
    AMOUNT,
    CATEGORY,
    NAME,
    TAGS,
    TOTAL_BUDGET,
)
from backend.constants.tables import TransactionsTableFields
from backend.repositories.budget_repository import BudgetRepository
from backend.services.budget.ledger import assign_claims, is_all_tags
from backend.services.budget.rules import BudgetRuleStore
from backend.services.budget_month_override_service import BudgetMonthOverrideService
from backend.services.pending_refunds_service import (
    GROSS_AMOUNT_COLUMN,
    PendingRefundsService,
    apply_refund_amount_adjustments,
)
from backend.services.tagging_service import CategoriesTagsService
from backend.services.transaction_views import NON_EXPENSE_CATEGORIES
from backend.services.transactions_service import TransactionsService
from backend.utils import data_cache

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

    def __init__(self, db: Session) -> None:
        """
        Initialize the budget service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.budget_repository = BudgetRepository(db)
        self.rules = BudgetRuleStore(db)
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
            All budget rules, of every kind. The ``tags`` column is a list of
            strings instead of the raw semicolon-separated string stored in
            the DB.
        """
        return self.rules.all()

    def update_rule(self, id_: int, **fields: Any) -> None:
        """
        Edit a budget rule of any kind, validated by its own kind.

        Parameters
        ----------
        id_ : int
            ID of the budget rule to update.
        **fields
            ``name``, ``amount``, ``category`` and/or ``tags``.

        Raises
        ------
        ValidationException
            If a key is not editable, or the edited rule fails validation.
        EntityNotFoundException
            If no rule with ``id_`` exists.
        """
        self.rules.update(id_, **fields)

    def delete_rule(self, id_: int) -> None:
        """
        Delete a budget rule by ID; see :meth:`BudgetRuleStore.delete`.

        Raises
        ------
        ValidationException
            If the rule is a month's or project's total rule.
        EntityNotFoundException
            If no rule with ``id_`` exists.
        """
        self.rules.delete(id_)

    _is_all_tags = staticmethod(is_all_tags)

    def _copy_rules(
        self,
        source_rules: pd.DataFrame,
        *,
        conflict_period_type: str,
        target_year: int,
        target_month: int | None = None,
        kind: str,
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
        kind : str
            Kind of the copies (``"monthly"`` or ``"yearly"``).
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
            if total_budget_passthrough and (
                rule[CATEGORY] == TOTAL_BUDGET or not tags
            ):
                kept, dropped = tags, []
            else:
                kept, dropped = self.rules.strip_conflicting_tags(
                    rule[CATEGORY], tags, target_year, conflict_period_type
                )
            skipped.extend(dropped)
            if total_budget_passthrough:
                if tags and not kept:
                    continue
            elif not kept:
                continue
            self.rules.insert(
                rule[NAME],
                rule[AMOUNT],
                rule[CATEGORY],
                kept,
                target_month,
                target_year,
                kind=kind,
            )
        return skipped

    @staticmethod
    def _expense_rows(all_data: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of ``all_data`` without non-expense categories, dates parsed."""
        expenses = all_data.loc[
            ~all_data[TransactionsTableFields.CATEGORY.value].isin(
                NON_EXPENSE_CATEGORIES
            )
        ].copy()
        expenses[TransactionsTableFields.DATE.value] = pd.to_datetime(
            expenses[TransactionsTableFields.DATE.value]
        )
        return expenses

    @staticmethod
    def _drop_split_parents(rows: pd.DataFrame) -> pd.DataFrame:
        """Return ``rows`` without split-parent transactions, whose splits carry the amount."""
        if "type" not in rows.columns:
            return rows
        return rows[rows["type"] != "split_parent"]

    def get_claims(self) -> pd.DataFrame:
        """
        Return every expense row with its budget month and the pool that owns it.

        The single source every budget figure aggregates from — see
        :mod:`backend.services.budget.ledger`. Rows are the budget's expenses
        (non-expense categories and split parents out), netted against the
        refunds matched to them plus the still-expected part of open pending
        refunds; each row's pre-netting amount is kept in
        :data:`GROSS_AMOUNT_COLUMN` for the transaction lists, which show the
        real figures.

        Every budget read aggregates from this ledger, and a Budget page opens
        several at once — the month, its neighbours, the trend, the alerts,
        the overview — each of which recomputed it over the whole history.
        It is shared through ``data_cache`` instead, so the first read after a
        write pays for it and the rest reuse it until the next commit.

        Returns
        -------
        pd.DataFrame
            Expense rows with ``budget_year``, ``budget_month``,
            ``claim_kind`` and ``claim_rule_id`` added — a copy the caller may
            change.
        """
        return data_cache.cached(
            self.db, ("budget.get_claims",), self._compute_claims
        ).copy()

    def _compute_claims(self) -> pd.DataFrame:
        """Build the claim ledger behind :meth:`get_claims`'s cache."""
        expenses = self.transactions_service.get_data_for_analysis()
        if not expenses.empty:
            expenses = self._drop_split_parents(self._expense_rows(expenses))
            expenses = apply_refund_amount_adjustments(
                expenses,
                self.pending_refunds_service.get_refund_amount_adjustments(
                    exclude_open=True
                ),
                keep_gross_in=GROSS_AMOUNT_COLUMN,
            )
        return assign_claims(
            expenses,
            self.rules.all(),
            self.month_override_service.get_override_map(),
        )

    def get_filtered_expenses(
        self,
        exclude_pending_refunds: bool = True,
        include_split_parents: bool = False,
        net_refunds: bool = False,
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
        net_refunds : bool, optional
            When ``True``, net matched refunds against the purchases they pay
            back by amount instead of dropping whole rows, so a refund cancels
            its purchase across any month gap and a partly-refunded purchase
            keeps the part still unrecovered. The pre-netting amount is kept
            in :data:`GROSS_AMOUNT_COLUMN` so a caller that lists the
            underlying transactions can restore it (see
            :func:`restore_gross_amounts`) — totals net, rows do not.
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

        expenses = self._expense_rows(all_data)
        projects = self.budget_repository.read_project_category_names()
        if projects:
            expenses = expenses.loc[
                ~expenses[TransactionsTableFields.CATEGORY.value].isin(projects)
            ]

        # Netting supersedes the row-drop: it removes the same money and more
        # (the refund transactions, and cross-month matches), so running both
        # would double-count the exclusion.
        if net_refunds:
            adjustments = self.pending_refunds_service.get_refund_amount_adjustments(
                exclude_open=exclude_pending_refunds
            )
            expenses = apply_refund_amount_adjustments(
                expenses, adjustments, keep_gross_in=GROSS_AMOUNT_COLUMN
            )
        elif exclude_pending_refunds:
            pending_refs = self.pending_refunds_service.get_active_pending_identifiers()
            tx_keys = pending_refs["transaction_keys"]
            split_ids = pending_refs["split_ids"]

            if tx_keys:
                # `unique_id` is a per-table auto-increment, so it must be
                # paired with the source table — matching on the bare id would
                # also drop the same-numbered transaction in every other table.
                keys = pd.Series(
                    list(
                        zip(
                            expenses[TransactionsTableFields.SOURCE.value],
                            expenses[TransactionsTableFields.UNIQUE_ID.value],
                            strict=True,
                        )
                    ),
                    index=expenses.index,
                )
                expenses = expenses[~keys.isin(tx_keys)]
            if TransactionsTableFields.SPLIT_ID.value in expenses.columns:
                expenses = expenses[
                    ~expenses[TransactionsTableFields.SPLIT_ID.value].isin(split_ids)
                ]

        return self._drop_split_parents(expenses)
