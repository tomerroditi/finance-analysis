"""
Cash-flow aggregations for the analysis service.

Provides the ``CashflowMixin`` with income/expense/debt-over-time series,
income-by-source and expenses-by-category breakdowns, and the shared
income/investment/expense mask helpers. Mixed into ``AnalysisService``
(see ``core.py``).
"""

from datetime import date

import pandas as pd

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

    def get_income_expenses_over_time(self, exclude_projects: bool = False, exclude_liabilities: bool = False, exclude_refunds: bool = False):
        """
        Aggregate income and expenses by month over time.

        Credit card transactions are excluded to avoid double-counting
        (bank debits already capture the net payment).

        Parameters
        ----------
        exclude_projects : bool, optional
            If True, exclude transactions whose category matches a project
            budget name. Defaults to False.

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

        if exclude_projects:
            from backend.services.budget_service import ProjectBudgetService

            project_names = ProjectBudgetService(self.db).get_all_projects_names()
            if project_names:
                df = df[~df[TransactionsTableFields.CATEGORY.value].isin(project_names)]

        if exclude_liabilities:
            df = df[df[TransactionsTableFields.CATEGORY.value] != LIABILITIES_CATEGORY]

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
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

        salary_df["month"] = pd.to_datetime(salary_df["date"]).dt.strftime("%Y-%m")
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

        liabilities["month"] = pd.to_datetime(liabilities["date"]).dt.strftime("%Y-%m")
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

    def get_expenses_by_category_over_time(self):
        """
        Get monthly expenses broken down by category over time.

        Returns
        -------
        list[dict]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``categories`` – dict mapping category name to expense amount (positive).
        """
        df = self.repo.get_itemized_transactions()

        if df.empty:
            return []

        # Regular expenses + negative liabilities (debt payments)
        regular_expense_mask = ~df["category"].isin(NON_EXPENSE_CATEGORIES) & (df["amount"] < 0)
        debt_payment_mask = (df["category"] == LIABILITIES_CATEGORY) & (df["amount"] < 0)
        expense_mask = regular_expense_mask | debt_payment_mask
        expenses = df[expense_mask].copy()
        # Use tag as label for liabilities to show loan names
        liabilities_mask = expenses["category"] == LIABILITIES_CATEGORY
        expenses.loc[liabilities_mask, "category"] = expenses.loc[liabilities_mask, TransactionsTableFields.TAG.value].fillna(LIABILITIES_CATEGORY)
        expenses["category"] = expenses["category"].fillna("Uncategorized")
        expenses["month"] = pd.to_datetime(expenses["date"]).dt.strftime("%Y-%m")

        pivot = expenses.groupby(["month", "category"])["amount"].sum().mul(-1).unstack(fill_value=0)

        return [
            {"month": month, "categories": {cat: round(float(val), 2) for cat, val in row.items() if val > 0}}
            for month, row in pivot.iterrows()
        ]

    def get_expenses_by_category(self):
        """
        Get expenses and refunds grouped by category.

        Non-expense categories (Ignore, Salary, Other Income, Investments,
        Liabilities) are excluded. Transactions with no category are grouped
        as ``"Uncategorized"``. Categories with positive net amounts are treated
        as refunds; those with negative net amounts are expenses.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``expenses`` – list of ``{"category": str, "amount": float}`` dicts
              (positive absolute values) for categories with net negative spend.
            - ``refunds`` – list of ``{"category": str, "amount": float}`` dicts
              for categories with net positive amounts (refunds exceed spend).
        """
        df = self.repo.get_itemized_transactions()

        if df.empty:
            return {"expenses": [], "refunds": []}

        expense_mask = ~df["category"].isin(NON_EXPENSE_CATEGORIES)
        expenses = df[expense_mask].copy()
        expenses["category"] = expenses["category"].fillna("Uncategorized")
        grouped = expenses.groupby("category")["amount"].sum()
        neg_grouped = grouped[grouped < 0].abs()
        pos_grouped = grouped[grouped > 0]
        return {
            "expenses": [
                {"category": cat, "amount": float(amt)}
                for cat, amt in neg_grouped.items()
            ],
            "refunds": [
                {"category": cat, "amount": float(amt)}
                for cat, amt in pos_grouped.items()
            ],
        }

    def get_income_by_source_over_time(self) -> list[dict]:
        """
        Get monthly income broken down by source (category+tag combination).

        Returns
        -------
        list[dict]
            List of ``{month, sources: {label: amount}, total}`` records
            ordered chronologically. Prior Wealth transactions are excluded.
        """
        df = self.repo.get_table()

        if df.empty:
            return []

        # Exclude credit card and insurance transactions (same as other income methods)
        df = df[~df["source"].isin(self.repo._CASHFLOW_EXCLUDED)]

        if df.empty:
            return []

        # Filter to income rows only
        income_mask = self._get_income_mask(df)
        income_df = df[income_mask].copy()

        # Exclude Prior Wealth transactions
        income_df = income_df[income_df["tag"] != PRIOR_WEALTH_TAG]

        if income_df.empty:
            return []

        income_df = self._add_source_label_column(income_df)

        income_df["month"] = pd.to_datetime(income_df["date"]).dt.strftime("%Y-%m")

        result = []
        for month, month_df in income_df.groupby("month", sort=True):
            sources = {}
            for label, group in month_df.groupby("source_label"):
                sources[label] = round(float(group["amount"].sum()), 2)
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

        parsed = pd.to_datetime(income_df["date"])
        if start is not None:
            income_df = income_df[parsed >= pd.Timestamp(start)]
            parsed = pd.to_datetime(income_df["date"])
        if end is not None:
            income_df = income_df[parsed <= pd.Timestamp(end)]
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
