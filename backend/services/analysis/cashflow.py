"""
Cash-flow aggregations for the analysis service.

Provides the ``CashflowMixin`` with income/expense/debt-over-time series,
income-by-source and expenses-by-category-over-time breakdowns, and the
income/investments/expenses totals. Which rows count as what lives in
``backend.services.transaction_views``. Mixed into
``AnalysisService`` (see ``core.py``).
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from backend.constants.categories import LIABILITIES_CATEGORY
from backend.constants.tables import TransactionsTableFields
from backend.services.transaction_views import TransactionView
from backend.utils.dataframe_dates import to_month_series


class CashflowMixin:
    """Cash-flow aggregation methods for ``AnalysisService``."""

    def get_income_expenses_over_time(
        self,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
        exclude_refunds: bool = False,
        exclude_pending_refunds: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Aggregate income and expenses by month over time.

        Read off the bank view: a card statement counts once, as the bank
        debit that paid it.

        Parameters
        ----------
        exclude_projects : bool, optional
            If True, exclude transactions whose category matches a project
            budget name. Defaults to False.
        exclude_liabilities : bool, optional
            If True, drop the Liabilities category entirely. Defaults to False.
        exclude_refunds : bool, optional
            If True, ignore *unmatched* refunds — a positive amount in an
            expense category, or a negative one in an income category — so the
            figures are gross rather than net. Defaults to False.
        exclude_pending_refunds : bool, optional
            Passed to :meth:`TransactionViews.bank`: whether a purchase still
            awaiting its refund is dropped. Matched refunds are netted either
            way. Defaults to True.

        Returns
        -------
        list[dict[str, Any]]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``income`` – total income for the month.
            - ``investments`` – net money moved into investments (positive
              for deposits).
            - ``expenses`` – total expenses for the month (absolute value).
        """
        view = self.views.bank(
            exclude_pending_refunds=exclude_pending_refunds,
            exclude_projects=exclude_projects,
            exclude_liabilities=exclude_liabilities,
        )
        if not view.months:
            return []

        income = view.income
        expenses = view.expenses
        if exclude_refunds:
            income = income[income["amount"] > 0]
            expenses = expenses[expenses["amount"] < 0]
        monthly = TransactionView(
            rows=pd.concat([income, expenses, view.investments]), months=view.months
        ).monthly()

        return [
            {
                "month": month,
                "income": float(row["income"]),
                "investments": float(row["investments"]),
                "expenses": float(row["expenses"]),
            }
            for month, row in monthly.iterrows()
        ]

    def get_debt_payments_over_time(self) -> list[dict[str, Any]]:
        """
        Aggregate debt (liability) payments by month over time.

        Only negative-amount Liabilities transactions are included
        (actual debt repayments, not loan receipts).

        Returns
        -------
        list[dict[str, Any]]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``amount`` – total debt payments for the month (positive value).
            - ``tags`` – payments per liability tag (positive values only).
        """
        expenses = self.views.bank(exclude_pending_refunds=False).expenses
        liabilities = expenses[
            expenses[TransactionsTableFields.CATEGORY.value] == LIABILITIES_CATEGORY
        ].copy()

        if liabilities.empty:
            return []

        liabilities["month"] = to_month_series(liabilities["date"])
        liabilities["tag"] = liabilities[TransactionsTableFields.TAG.value].fillna(
            "Uncategorized"
        )

        pivot = (
            liabilities.groupby(["month", "tag"])[TransactionsTableFields.AMOUNT.value]
            .sum()
            .mul(-1)
            .unstack(fill_value=0)
        )

        return [
            {
                "month": month,
                "amount": round(float(row.sum()), 2),
                "tags": {
                    tag: round(float(val), 2) for tag, val in row.items() if val > 0
                },
            }
            for month, row in pivot.iterrows()
        ]

    def _add_source_label_column(self, income_df: pd.DataFrame) -> pd.DataFrame:
        """Add a vectorized ``source_label`` column to an income frame.

        Loan receipts label as ``"Loans[ / tag]"``, everything else as
        ``"<category>[ / <tag>]"``.

        Parameters
        ----------
        income_df : pd.DataFrame
            Income-only transactions with ``category``, ``tag``, ``amount``.

        Returns
        -------
        pd.DataFrame
            The same frame with ``source_label`` added.
        """
        category = income_df["category"]
        tag = income_df["tag"]
        amount = income_df["amount"]
        tag_present = tag.notna() & (tag != "")
        tag_str = tag.astype(object)

        is_loan = (category == LIABILITIES_CATEGORY) & (amount > 0)
        loan_label = np.where(tag_present, "Loans / " + tag_str.astype(str), "Loans")
        non_loan_label = np.where(
            tag_present, category.astype(str) + " / " + tag_str.astype(str), category
        )
        income_df["source_label"] = np.where(is_loan, loan_label, non_loan_label)
        return income_df

    def get_expenses_by_category_over_time(
        self,
        exclude_pending_refunds: bool = True,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get monthly expenses broken down by category over time.

        A refund is netted against the category of the purchase it repays, not
        its own: the refund row is zeroed wherever it sits and the purchase is
        reduced, so the money never moves between categories. A refund with no
        purchase to match is netted against the category it lands in, which is
        why a month's category total can come out negative — more money came
        back than went out. Callers that draw a category (a bar segment, a pie
        slice) skip those; callers that total a month must keep them, or the
        refund silently disappears from the month it belongs to.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            Passed to :meth:`TransactionViews.spending`. Defaults to True.
        exclude_projects : bool, optional
            If True, drop categories that are project-budget names — planned
            lumpy spending the caller may want out of its ordinary-spend view.
            Defaults to False.
        exclude_liabilities : bool, optional
            If True, drop debt payments (negative ``Liabilities`` rows).
            Defaults to False, because the money did leave the account; a
            caller taking the envelope view of spending (where loan principal
            is a transfer into net worth rather than consumption) passes True.

        Returns
        -------
        list[dict[str, Any]]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``categories`` – dict mapping category name to expense amount
              (positive for spend, negative for a category left in credit).
        """
        expenses = self.views.spending(
            exclude_pending_refunds=exclude_pending_refunds,
            exclude_projects=exclude_projects,
            exclude_liabilities=exclude_liabilities,
        ).expenses.copy()

        if expenses.empty:
            return []

        # Use tag as label for liabilities to show loan names
        liabilities_mask = expenses["category"] == LIABILITIES_CATEGORY
        expenses.loc[liabilities_mask, "category"] = expenses.loc[
            liabilities_mask, TransactionsTableFields.TAG.value
        ].fillna(LIABILITIES_CATEGORY)
        expenses["category"] = expenses["category"].fillna("Uncategorized")
        expenses["month"] = to_month_series(expenses["date"])

        pivot = (
            expenses.groupby(["month", "category"])["amount"]
            .sum()
            .mul(-1)
            .unstack(fill_value=0)
        )

        return [
            {
                "month": month,
                "categories": {
                    cat: round(float(val), 2) for cat, val in row.items() if val != 0
                },
            }
            for month, row in pivot.iterrows()
        ]

    def get_income_by_source_over_time(
        self, exclude_pending_refunds: bool = True, exclude_liabilities: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get monthly income broken down by source (category+tag combination).

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            Passed to :meth:`TransactionViews.bank`. A refund that landed in an
            income category is money coming back, not earnings, so netting it
            keeps it out of the breakdown. Defaults to True.
        exclude_liabilities : bool, optional
            If True, drop loan receipts (positive ``Liabilities`` rows). This
            is the income half of the same switch that drops debt payments
            from the expense breakdown: taking a loan out of the outflow while
            leaving the money it paid in as income would report a household as
            saving the whole loan. Defaults to False.

        Returns
        -------
        list[dict[str, Any]]
            List of ``{month, sources: {label: amount}, total}`` records
            ordered chronologically. Prior Wealth transactions are excluded.
        """
        income_df = self.views.bank(
            exclude_pending_refunds=exclude_pending_refunds,
            exclude_liabilities=exclude_liabilities,
        ).income.copy()

        if income_df.empty:
            return []

        income_df = self._add_source_label_column(income_df)

        income_df["month"] = to_month_series(income_df["date"])

        result: list[dict[str, Any]] = []
        for month, month_df in income_df.groupby("month", sort=True):
            sources: dict[str, float] = {}
            for label, group in month_df.groupby("source_label"):
                # A source fully netted away by a matched refund contributes
                # nothing; carrying it as a zero would only add a label the
                # chart cannot draw.
                amount = round(float(group["amount"].sum()), 2)
                if amount > 0:
                    sources[label] = amount
            total = round(sum(sources.values()), 2)
            result.append({"month": month, "sources": sources, "total": total})

        return result

    def get_income_by_source(
        self, start: date | None = None, end: date | None = None
    ) -> dict[str, Any]:
        """
        Aggregate total income amount per source within a date window.

        "Income source" is the category+tag label (same as
        ``get_income_by_source_over_time``) and the rows are that chart's:
        the bank view's income, a matched refund netted against its purchase.

        Parameters
        ----------
        start, end : date | None
            Inclusive date bounds. ``None`` means unbounded (all time).

        Returns
        -------
        dict
            ``{sources: [{label, amount, share}], total, start, end}`` where
            ``sources`` is sorted by ``amount`` descending and ``share`` is the
            fraction of ``total``. ``start``/``end`` echo the resolved window as
            ISO strings (or ``None``).
        """
        empty = {
            "sources": [],
            "total": 0.0,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        }

        income_df = self.views.bank().between(start, end).income
        if income_df.empty:
            return empty

        income_df = self._add_source_label_column(income_df)
        grouped = income_df.groupby("source_label")["amount"].sum()
        grouped = grouped[grouped.round(2) > 0]
        total = float(grouped.sum())

        sources = [
            {
                "label": label,
                "amount": round(float(amount), 2),
                "share": round(float(amount) / total, 4) if total else 0.0,
            }
            for label, amount in grouped.items()
        ]
        sources.sort(key=lambda s: s["amount"], reverse=True)

        return {
            "sources": sources,
            "total": round(total, 2),
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        }
