"""
Cash-flow aggregations for the analysis service.

Provides the ``CashflowMixin`` with income/expense/debt-over-time series,
income-by-source and expenses-by-category-over-time breakdowns, and the shared
income/investment/expense mask helpers. Mixed into ``AnalysisService``
(see ``core.py``).
"""

from datetime import date

import pandas as pd

from backend.utils.dataframe_dates import to_month_series
from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    LIABILITIES_CATEGORY,
    NON_EXPENSE_CATEGORIES,
    IncomeCategories,
)
from backend.constants.tables import TransactionsTableFields
from backend.services.transaction_classification import (
    income_mask,
    investment_mask,
    transactions_masks,
)


class CashflowMixin:
    """Cash-flow aggregation methods for ``AnalysisService``."""

    def _net_matched_refunds(
        self, df: pd.DataFrame, exclude_pending_refunds: bool
    ) -> pd.DataFrame:
        """
        Net refunds matched to a purchase out of both sides of a frame.

        A refund and the purchase it pays back are one event, but they rarely
        share a month, and an unlinked positive amount can only ever net
        against the month it lands in. ``refund_links`` records which purchase
        each incoming transaction repays, so the matched money is taken off
        the purchase and off the refund alike, whatever months they fell in,
        and neither shows up as that month's expense or income.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions frame to net, straight from the repository.
        exclude_pending_refunds : bool
            Whether a still-outstanding expectation is dropped from its
            purchase as well — the card's "Pending Refunds Excluded" chip.

        Returns
        -------
        pd.DataFrame
            The frame with ``amount`` netted.
        """
        # Local import: pending_refunds_service imports the transactions
        # repository, which the analysis service is itself constructed with.
        from backend.services.pending_refunds_service import (
            PendingRefundsService,
            apply_refund_amount_adjustments,
        )

        adjustments = PendingRefundsService(self.db).get_refund_amount_adjustments(
            exclude_open=exclude_pending_refunds
        )
        return apply_refund_amount_adjustments(df, adjustments)

    @staticmethod
    def _filter_date_window(
        df: pd.DataFrame, start: date | None, end: date | None
    ) -> pd.DataFrame:
        """
        Keep only the rows whose ``date`` falls inside an inclusive window.

        Parameters
        ----------
        df : pd.DataFrame
            Frame carrying a ``date`` column.
        start, end : date | None
            Inclusive bounds. ``None`` means unbounded on that side, so both
            ``None`` returns the frame untouched.

        Returns
        -------
        pd.DataFrame
            The rows inside the window.
        """
        if df.empty or (start is None and end is None):
            return df
        parsed = pd.to_datetime(df["date"])
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= parsed >= pd.Timestamp(start)
        if end is not None:
            mask &= parsed <= pd.Timestamp(end)
        return df[mask]

    def get_income_expenses_over_time(
        self,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
        exclude_refunds: bool = False,
        exclude_pending_refunds: bool = True,
    ):
        """
        Aggregate income and expenses by month over time.

        Credit card transactions are excluded to avoid double-counting
        (bank debits already capture the net payment).

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
            Passed to :meth:`_net_matched_refunds`: whether a purchase still
            awaiting its refund is dropped. Matched refunds are netted either
            way. Defaults to True.

        Returns
        -------
        list[dict]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``income`` – total income for the month.
            - ``expenses`` – total expenses for the month (absolute value).
        """
        df = self.repo.get_table()

        if df.empty:
            return []

        df = self._net_matched_refunds(df, exclude_pending_refunds)

        if exclude_projects:
            from backend.services.budget_service import ProjectBudgetService

            project_names = ProjectBudgetService(self.db).get_all_projects_names()
            if project_names:
                df = df[~df[TransactionsTableFields.CATEGORY.value].isin(project_names)]

        if exclude_liabilities:
            df = df[df[TransactionsTableFields.CATEGORY.value] != LIABILITIES_CATEGORY]

        df["month"] = to_month_series(df["date"])
        # Month index from the *pre-exclusion* frame: a CC-only month must
        # still appear (with zeros), matching the historical per-month loop.
        months = sorted(df["month"].unique())

        flow = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]
        masks = self.get_transactions_masks(flow)

        income_amounts = flow["amount"].where(masks["income"], 0.0)
        expense_amounts = flow["amount"].where(masks["expenses"], 0.0)
        if exclude_refunds:
            income_amounts = income_amounts.where(flow["amount"] > 0, 0.0)
            expense_amounts = expense_amounts.where(flow["amount"] < 0, 0.0)
        investment_amounts = flow["amount"].where(masks["investments"], 0.0)

        grouped = (
            pd.DataFrame(
                {
                    "month": flow["month"],
                    "income": income_amounts,
                    "investments": investment_amounts,
                    "expenses": expense_amounts,
                }
            )
            .groupby("month")
            .sum()
            .reindex(months, fill_value=0.0)
        )

        return [
            {
                "month": month,
                "income": float(row["income"]),
                "investments": float(row["investments"]) * -1,
                "expenses": float(row["expenses"]) * -1,
            }
            for month, row in grouped.iterrows()
        ]

    def get_avg_monthly_salary(self, months: int = 6) -> float | None:
        """Compute average monthly salary income over the last N months.

        Filters transactions by the Salary category and averages the
        per-month totals over the most recent ``months`` months that
        have at least one salary transaction.

        Parameters
        ----------
        months : int
            Number of recent months to average over.

        Returns
        -------
        float or None
            Average monthly salary, or None if no salary data exists.
        """
        df = self.repo.get_table()
        if df.empty:
            return None

        salary_df = df[df[TransactionsTableFields.CATEGORY.value] == IncomeCategories.SALARY.value].copy()
        if salary_df.empty:
            return None

        salary_df["month"] = to_month_series(salary_df["date"])
        monthly_totals = salary_df.groupby("month")["amount"].sum()
        recent = monthly_totals.sort_index().tail(months)
        if recent.empty:
            return None

        return float(recent.mean())

    def get_debt_payments_over_time(self):
        """
        Aggregate debt (liability) payments by month over time.

        Only negative-amount Liabilities transactions are included
        (actual debt repayments, not loan receipts).

        Returns
        -------
        list[dict]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``amount`` – total debt payments for the month (positive value).
        """
        df = self.repo.get_table()

        if df.empty:
            return []

        df = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]
        liabilities = df[
            (df[TransactionsTableFields.CATEGORY.value] == LIABILITIES_CATEGORY)
            & (df[TransactionsTableFields.AMOUNT.value] < 0)
        ].copy()

        if liabilities.empty:
            return []

        liabilities["month"] = to_month_series(liabilities["date"])
        liabilities["tag"] = liabilities[TransactionsTableFields.TAG.value].fillna("Uncategorized")

        pivot = liabilities.groupby(["month", "tag"])[TransactionsTableFields.AMOUNT.value].sum().mul(-1).unstack(fill_value=0)

        return [
            {
                "month": month,
                "amount": round(float(row.sum()), 2),
                "tags": {tag: round(float(val), 2) for tag, val in row.items() if val > 0},
            }
            for month, row in pivot.iterrows()
        ]

    def get_income_investments_and_expenses(
        self, df: pd.DataFrame, exclude_refunds: bool = False
    ) -> tuple[float, float, float]:
        """
        Calculate total income, investments, and expenses from a transactions DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame (typically the full merged table).
        exclude_refunds : bool, optional
            If True, only count positive amounts as income and negative amounts
            as expenses (exclude refunds/reversals). Defaults to False.

        Returns
        -------
        tuple[float, float, float]
            A ``(income, investments, expenses)`` triple where income and expenses
            are non-negative. ``expenses`` is the absolute value of negative amounts.
        """
        df = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]

        income_mask, investment_mask, expenses_mask = self.get_transactions_masks(df).values()

        income_df = df[income_mask]
        expense_df = df[expenses_mask]

        if exclude_refunds:
            income_df = income_df[income_df["amount"] > 0]
            expense_df = expense_df[expense_df["amount"] < 0]

        income = float(income_df["amount"].sum())
        investments = float(df[investment_mask]["amount"].sum()) * -1
        expenses = float(expense_df["amount"].sum()) * -1
        return income, investments, expenses

    def get_transactions_masks(self, df: pd.DataFrame) -> dict[str, pd.Series]:
        """
        Get boolean masks for income, investments, and expenses.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame (typically the full merged table).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys "income", "investments", and "expenses" mapping to
            boolean Series aligned with ``df``.
        """
        return transactions_masks(df)

    def _get_income_mask(self, df: pd.DataFrame) -> pd.Series:
        """
        Build a boolean mask identifying income rows in a transactions DataFrame.

        A row is classified as income if its category is in ``IncomeCategories``,
        or if its category is exactly ``Liabilities_CATEGORY`` with a positive amount
        (loan receipts / liability refunds).

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame with at least ``category`` and ``amount`` columns.

        Returns
        -------
        pd.Series
            Boolean Series aligned with ``df`` — ``True`` for income rows.
        """
        return income_mask(df)

    def _get_investment_mask(self, df: pd.DataFrame) -> pd.Series:
        """
        Build a boolean mask identifying investment rows in a transactions DataFrame.

        A row is classified as an investment if its category is exactly ``INVESTMENTS_CATEGORY``.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame with at least a ``category`` column.

        Returns
        -------
        pd.Series
            Boolean Series aligned with ``df`` — ``True`` for investment rows.
        """
        return investment_mask(df)

    def _add_source_label_column(self, income_df: pd.DataFrame) -> pd.DataFrame:
        """Add a vectorized ``source_label`` column to an income frame.

        Vectorized equivalent of the per-row ``_income_source_label``:
        loan receipts label as ``"Loans[ / tag]"``, everything else as
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
        import numpy as np

        category = income_df["category"]
        tag = income_df["tag"]
        amount = income_df["amount"]
        tag_present = tag.notna() & (tag != "")
        tag_str = tag.astype(object)

        is_loan = (category == LIABILITIES_CATEGORY) & (amount > 0)
        loan_label = np.where(
            tag_present, "Loans / " + tag_str.astype(str), "Loans"
        )
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
    ):
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
            Passed to :meth:`_net_matched_refunds`. Defaults to True.
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
        list[dict]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``categories`` – dict mapping category name to expense amount
              (positive for spend, negative for a category left in credit).
        """
        df = self.repo.get_itemized_transactions()

        if df.empty:
            return []

        df = self._net_matched_refunds(df, exclude_pending_refunds)

        # Expense categories at any sign — a positive row in one is a refund,
        # and it belongs in its category's total, not dropped. Liabilities is
        # the exception: a positive one is a loan receipt, which is income.
        regular_expense_mask = ~df["category"].isin(NON_EXPENSE_CATEGORIES)
        debt_payment_mask = (df["category"] == LIABILITIES_CATEGORY) & (df["amount"] < 0)
        expense_mask = (
            regular_expense_mask
            if exclude_liabilities
            else regular_expense_mask | debt_payment_mask
        )
        expenses = df[expense_mask].copy()

        if exclude_projects:
            from backend.services.budget_service import ProjectBudgetService

            project_names = ProjectBudgetService(self.db).get_all_projects_names()
            if project_names:
                expenses = expenses[
                    ~expenses[TransactionsTableFields.CATEGORY.value].isin(project_names)
                ]

        if expenses.empty:
            return []

        # Use tag as label for liabilities to show loan names
        liabilities_mask = expenses["category"] == LIABILITIES_CATEGORY
        expenses.loc[liabilities_mask, "category"] = expenses.loc[liabilities_mask, TransactionsTableFields.TAG.value].fillna(LIABILITIES_CATEGORY)
        expenses["category"] = expenses["category"].fillna("Uncategorized")
        expenses["month"] = to_month_series(expenses["date"])

        pivot = expenses.groupby(["month", "category"])["amount"].sum().mul(-1).unstack(fill_value=0)

        return [
            {"month": month, "categories": {cat: round(float(val), 2) for cat, val in row.items() if val != 0}}
            for month, row in pivot.iterrows()
        ]

    def get_income_by_source_over_time(
        self, exclude_pending_refunds: bool = True, exclude_liabilities: bool = False
    ) -> list[dict]:
        """
        Get monthly income broken down by source (category+tag combination).

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            Passed to :meth:`_net_matched_refunds`. A refund that landed in an
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
        list[dict]
            List of ``{month, sources: {label: amount}, total}`` records
            ordered chronologically. Prior Wealth transactions are excluded.
        """
        df = self.repo.get_table()

        if df.empty:
            return []

        df = self._net_matched_refunds(df, exclude_pending_refunds)

        # Exclude credit card and insurance transactions (same as other income methods)
        df = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]

        if df.empty:
            return []

        # Filter to income rows only
        income_mask = self._get_income_mask(df)
        income_df = df[income_mask].copy()

        # Exclude Prior Wealth transactions
        income_df = income_df[income_df["tag"] != PRIOR_WEALTH_TAG]

        if exclude_liabilities:
            income_df = income_df[income_df["category"] != LIABILITIES_CATEGORY]

        if income_df.empty:
            return []

        income_df = self._add_source_label_column(income_df)

        income_df["month"] = to_month_series(income_df["date"])

        result = []
        for month, month_df in income_df.groupby("month", sort=True):
            sources = {}
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
    ) -> dict:
        """
        Aggregate total income amount per source within a date window.

        "Income source" is the category+tag label (same as
        ``get_income_by_source_over_time``). Credit-card source and
        Prior Wealth transactions are excluded, matching the over-time chart.

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

        df = self.repo.get_table()
        if df.empty:
            return empty

        df = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]
        if df.empty:
            return empty

        income_df = df[self._get_income_mask(df)].copy()
        income_df = income_df[income_df["tag"] != PRIOR_WEALTH_TAG]
        if income_df.empty:
            return empty

        income_df = self._filter_date_window(income_df, start, end)
        if income_df.empty:
            return empty

        income_df = self._add_source_label_column(income_df)
        grouped = income_df.groupby("source_label")["amount"].sum()
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
