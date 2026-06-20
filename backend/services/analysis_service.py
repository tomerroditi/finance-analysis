from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    CREDIT_CARDS,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    NON_EXPENSE_CATEGORIES,
    IncomeCategories,
)
from backend.constants.tables import Tables, TransactionsTableFields
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.investments_service import InvestmentsService
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService


class AnalysisService:
    """
    Service for financial analysis and dashboard aggregations.

    Computes income/expense breakdowns, category summaries, net balance
    trends, Sankey diagram data, and net worth over time by querying
    transaction, bank balance, and investment repositories.
    """

    def __init__(self, db: Session):
        """
        Initialize the analysis service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = TransactionsRepository(db)
        self.balance_repo = BankBalanceRepository(db)
        self.investments_repo = InvestmentsRepository(db)
        self.investments_service = InvestmentsService(db)
        self.bank_balance_service = BankBalanceService(db)
        self.cash_balance_service = CashBalanceService(db)

    def get_overview(self):
        """
        Get a financial overview including totals and latest data date.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``latest_data_date`` – latest transaction date across all data.
            - ``total_income`` – total income (positive amounts) plus prior wealth.
            - ``total_expenses`` – total expenses (absolute value of negative amounts).
            - ``total_investments`` – current portfolio value across all open investments.
            - ``net_balance_change`` – income minus expenses.
        """
        df = self.repo.get_table()
        # On a fresh / empty DB the column exists (canonical empty schema)
        # but the max is NaT, which JSON can't serialize. Coerce to None.
        latest_date_val = df["date"].max() if not df.empty else None
        latest_date = (
            None
            if latest_date_val is None or pd.isna(latest_date_val)
            else latest_date_val
        )

        income, investments, expenses = self.get_income_investments_and_expenses(df)
        prior_wealth = self.bank_balance_service.get_total_prior_wealth() + self.investments_service.get_total_prior_wealth() + self.cash_balance_service.get_total_prior_wealth()
        income += prior_wealth

        return {
            "latest_data_date": latest_date,
            "total_income": income,
            "total_expenses": expenses,
            "total_investments": investments,
            "net_balance_change": income - expenses,
        }

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

        monthly_data = []
        for month in sorted(df["month"].unique()):
            month_df = df[df["month"] == month]
            income, investments, expenses = self.get_income_investments_and_expenses(
                month_df, exclude_refunds=exclude_refunds
            )
            monthly_data.append(
                {
                    "month": month,
                    "income": income,
                    "investments": investments,
                    "expenses": expenses,
                }
            )

        return monthly_data

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
        income_mask = self._get_income_mask(df)
        investment_mask = self._get_investment_mask(df)
        expenses_mask = ~income_mask & ~investment_mask

        return {
            "income": income_mask,
            "investments": investment_mask,
            "expenses": expenses_mask,
        }

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
        return df["category"].isin([c.value for c in IncomeCategories]) | (
            (df["category"] == LIABILITIES_CATEGORY)
            & (df["amount"] > 0)
        )
    
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
        return df["category"] == INVESTMENTS_CATEGORY

    def get_net_balance_over_time(self) -> list[dict]:
        """
        Get monthly net balance and cumulative balance over time.

        Credit card transactions are excluded to avoid double-counting.
        Cumulative balance is the running total starting from 0.

        Returns
        -------
        list[dict]
            Chronologically sorted list with one entry per month containing:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``net_change`` – sum of all transaction amounts for the month.
            - ``cumulative_balance`` – running total up to and including this month.
        """
        bank_prior_wealth = self.bank_balance_service.get_total_prior_wealth()
        investment_prior_wealth = self.investments_service.get_total_prior_wealth()
        cash_prior_wealth = self.cash_balance_service.get_total_prior_wealth()

        df = self.repo.get_cashflow_transactions()

        if df.empty:
            return []

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        cumulative = bank_prior_wealth + investment_prior_wealth + cash_prior_wealth


        trend = []
        trend.append(
            {
                "month": (pd.to_datetime(df["date"].min()) - pd.DateOffset(months=1)).strftime("%Y-%m"),
                "net_change": 0.0,
                "cumulative_balance": round(cumulative, 2),
            }
        )

        for month, group in df.groupby("month", sort=True):
            net_change = float(group["amount"].sum())
            cumulative += net_change

            trend.append(
                {
                    "month": month,
                    "net_change": round(net_change, 2),
                    "cumulative_balance": round(cumulative, 2),
                }
            )

        return trend

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

    def get_sankey_data(self) -> dict:
        """
        Get data for a two-layer Sankey (flow) diagram.

        Layer 1 flows: income sources → ``Total Income`` node.
        Layer 2 flows: ``Total Income`` node → expense destinations.

        Sources include: Salary, Prior Wealth, Other Income, Loans, and
        Wealth Deficit (added when expenses exceed income). Destinations
        include: per-category expenses, Paid Debt, and Wealth Growth
        (added when income exceeds expenses). Credit Cards and Ignore
        categories are excluded.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``nodes`` – list of node names sorted with ``Total Income`` first.
            - ``node_labels`` – list of node names in link-index order.
            - ``links`` – list of dicts with ``source`` (int), ``target`` (int),
              ``value`` (float), and ``label`` (str).
        """
        df = self.repo.get_itemized_transactions(include_split_parents=False)

        if df.empty:
            return {"nodes": [], "links": []}

        # Calculate CC gap before filtering out Credit Cards category
        bank_cc_payments = abs(df[df["category"] == CREDIT_CARDS]["amount"].sum())
        itemized_cc_total = abs(df[df["source"] == Tables.CREDIT_CARD.value]["amount"].sum())
        cc_gap = bank_cc_payments - itemized_cc_total

        df = df[df['category'] != CREDIT_CARDS]

        # --- Processing ---
        SALARY = IncomeCategories.SALARY.value
        OTHER_INCOME = IncomeCategories.OTHER_INCOME.value

        total_income_node = "Total Income"

        # Initialize Aggregates
        sources = {}  # name -> amount
        destinations = {}  # name -> amount
        helpers = {}  # name -> amount

        sources[SALARY] = df[df["category"] == SALARY]["amount"].sum()
        # Split out Prior Wealth from Other Income
        other_income_df = df[df["category"] == OTHER_INCOME]
        # Note: txn_prior_wealth now comes from cash_balances table instead of synthetic transaction
        from backend.services.cash_balance_service import CashBalanceService
        cash_prior_wealth = CashBalanceService(self.db).get_total_prior_wealth()
        txn_prior_wealth = cash_prior_wealth
        bank_prior_wealth = self.bank_balance_service.get_total_prior_wealth()
        investment_prior_wealth = self.investments_service.get_total_prior_wealth()
        sources[PRIOR_WEALTH_TAG] = txn_prior_wealth + bank_prior_wealth + investment_prior_wealth
        sources[OTHER_INCOME] = other_income_df[
            other_income_df["tag"] != PRIOR_WEALTH_TAG
        ]["amount"].sum()
        sources["Loans"] = df[(df["category"] == LIABILITIES_CATEGORY) & (df["amount"] > 0)][
            "amount"
        ].sum()
        # sources["Investments Withdrawal"] = df[(df['category'] == INVESTMENTS) & (df['amount'] > 0)]['amount'].sum()

        destinations["Paid Debt"] = abs(
            df[(df["category"] == LIABILITIES_CATEGORY) & (df["amount"] < 0)]["amount"].sum()
        )
        # destinations["Investments Deposit"] = abs(df[(df['category'] == INVESTMENTS) & (df['amount'] < 0)]['amount'].sum())

        exclude_cats = [SALARY, OTHER_INCOME, LIABILITIES_CATEGORY, INVESTMENTS_CATEGORY]
        expenses_df = df[~df["category"].isin(exclude_cats)]
        for cat, group in expenses_df.groupby("category"):
            net = group["amount"].sum()
            if net > 0:
                sources[f"Refunds: {cat}"] = net
            elif net < 0:
                destinations[cat] = abs(net)

        if cc_gap > 0:
            destinations["Unknown"] = cc_gap

        # TODO: we need to account for payments and allocations from filtered out data to correctly calculate it
        helpers["Debt To Be Paid"] = df[(df["category"] == LIABILITIES_CATEGORY)]["amount"].sum()
        net = sum(sources.values()) - sum(destinations.values())
        if net < 0:
            sources["Wealth Deficit"] = abs(net)
        else:
            destinations["Wealth Growth"] = net

        # --- Calculate Flows ---
        nodes: list[str] = []
        node_idx: dict[str, int] = {}
        links: list[dict] = []

        def get_node_idx(name) -> int:
            idx = node_idx.get(name)
            if idx is None:
                idx = len(nodes)
                nodes.append(name)
                node_idx[name] = idx
            return idx

        # Layer 1: Sources (income) -> grouped sources (salary, debt, wealth deficit)
        for name, val in sources.items():
            links.append(
                {
                    "source": get_node_idx(name),
                    "target": get_node_idx(total_income_node),
                    "value": round(val, 2),
                    "label": "",
                }
            )

        # Layer 2: Total Budget -> Destinations
        for name, val in destinations.items():
            links.append(
                {
                    "source": get_node_idx(total_income_node),
                    "target": get_node_idx(name),
                    "value": round(val, 2),
                    "label": "",
                }
            )

        return {
            "nodes": sorted(nodes, key=lambda x: (x != total_income_node, x)),
            "node_labels": nodes,
            "links": links,
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

        # Build source labels (vectorized equivalent of _income_source_label)
        import numpy as np

        category = income_df["category"]
        tag = income_df["tag"]
        amount = income_df["amount"]
        # A "truthy" tag mirrors the per-row checks: not NaN/None and not empty string.
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

        income_df["source_label"] = income_df.apply(self._income_source_label, axis=1)
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

    @staticmethod
    def _income_source_label(row: pd.Series) -> str:
        """
        Build a human-readable label for an income source.

        Parameters
        ----------
        row : pd.Series
            A transaction row with 'category', 'tag', and 'amount' fields.

        Returns
        -------
        str
            Label like "Salary", "Other Income / Freelance", or "Loans".
        """
        category = row["category"]

        # Positive liabilities = loans
        if category == LIABILITIES_CATEGORY and row["amount"] > 0:
            tag = row.get("tag")
            if pd.notna(tag) and tag:
                return f"Loans / {tag}"
            return "Loans"

        tag = row.get("tag")
        if pd.isna(tag) or tag is None or tag == "":
            return category
        return f"{category} / {tag}"

    def get_net_worth_over_time(self) -> list[dict]:
        """
        Get monthly net worth (bank balance + investment value + cash) over time.

        Bank balance is reconstructed as ``prior_wealth + cumulative bank transactions``.
        Investment value is the snapshot-resolved portfolio value at each
        month end (snapshot-first per investment, transaction-based fallback
        when no snapshot exists). This means market gains/losses recorded
        as snapshots flow through into both ``investment_value`` and ``net_worth``.
        Cash balance is reconstructed as ``cash_prior_wealth + cumulative cash transactions``.
        An anchor data point one month before the earliest transaction shows
        the pure prior-wealth baseline.

        Returns
        -------
        list[dict]
            List of monthly snapshots (anchor + one per month in range) with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``bank_balance`` – reconstructed bank balance at month end.
            - ``investment_value`` – snapshot-resolved investment value at month end.
            - ``cash`` – reconstructed cash balance at month end.
            - ``net_worth`` – ``bank_balance + investment_value + cash``.
        """
        bank_prior_wealth = self.bank_balance_service.get_total_prior_wealth()
        investment_prior_wealth = self.investments_service.get_total_prior_wealth()
        cash_prior_wealth = self.cash_balance_service.get_total_prior_wealth()
        prior_wealth_total = bank_prior_wealth + investment_prior_wealth

        # --- Bank transactions (all sources except credit card and insurance) ---
        df = self.repo.get_cashflow_transactions()

        if df.empty:
            return []

        df["date_parsed"] = pd.to_datetime(df["date"])
        df["month"] = df["date_parsed"].dt.strftime("%Y-%m")
        months = sorted(df["month"].unique())

        # --- Split cash off from bank-side cashflow ---
        # bank_df: bank + manual-investment transactions. Manual investment
        # deposits/withdrawals stay here because their offset is wired into
        # investment_prior_wealth, so they correctly drain/refill bank as
        # they happen. Cash lives only in the cash line.
        cash_mask = df["source"] == Tables.CASH.value
        cash_df = df[cash_mask]
        bank_df = df[~cash_mask]

        # --- Prior-wealth anchor point (1 month before earliest data) ---
        anchor_month = (pd.to_datetime(months[0] + "-01") - pd.DateOffset(months=1)).strftime("%Y-%m")

        result = [{
            "month": anchor_month,
            "bank_balance": round(prior_wealth_total, 2),
            "investment_value": 0.0,
            "cash": round(cash_prior_wealth, 2),
            "net_worth": round(prior_wealth_total + cash_prior_wealth, 2),
        }]

        for month in months:
            month_end = pd.to_datetime(month + "-01") + pd.offsets.MonthEnd(0)
            month_end_str = month_end.strftime("%Y-%m-%d")

            bank_balance = prior_wealth_total + float(
                bank_df.loc[bank_df["date_parsed"] <= month_end, "amount"].sum()
            )

            inv_value = self.investments_service.get_total_value_at_date(month_end_str)

            cash_balance = cash_prior_wealth + float(
                cash_df.loc[cash_df["date_parsed"] <= month_end, "amount"].sum()
            ) if not cash_df.empty else cash_prior_wealth

            result.append({
                "month": month,
                "bank_balance": round(bank_balance, 2),
                "investment_value": round(inv_value, 2),
                "cash": round(cash_balance, 2),
                "net_worth": round(bank_balance + inv_value + cash_balance, 2),
            })

        return result

    def get_cash_flow_forecast(self) -> dict:
        """Forecast the current month's cash flow from trend + month-to-date actuals.

        Projects where the month will end by combining what has already
        happened this month (income received, expenses spent) with a
        trend-based estimate of the remaining days. The expense trend is the
        rolling 3-month average (falling back to 6/12-month when sparse); the
        income trend is the average of the last 3 complete months. The
        projection never dips below money already spent.

        This is the data behind the dashboard "This Month" hero — the
        month-end balance projection and the "safe to spend" figure that
        Israeli budgeting apps (RiseUp et al.) lead with.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``month`` – current month in ``YYYY-MM`` format.
            - ``days_in_month`` / ``day_of_month`` / ``days_remaining`` – ints.
            - ``actual_income`` / ``actual_expenses`` – month-to-date totals
              (non-negative; expenses are the absolute value of outflows).
            - ``expected_income`` / ``expected_expenses`` – projected
              full-month totals.
            - ``projected_net`` – ``expected_income - expected_expenses``.
            - ``current_bank_balance`` – sum of tracked bank balances now.
            - ``projected_end_balance`` – bank balance projected to month end.
            - ``safe_to_spend`` – money left to spend freely this month:
              ``expected_income - actual_expenses - committed_remaining``
              (non-negative).
            - ``safe_to_spend_daily`` – ``safe_to_spend`` spread over the
              remaining days.
            - ``avg_monthly_income`` / ``avg_monthly_expenses`` – the trend
              baselines used.
            - ``committed_remaining`` – detected recurring charges whose next
              due date falls in the remainder of this month.
            - ``daily`` – per-day list of ``{date, actual_balance,
              projected_balance}`` for the trajectory chart (one is null
              depending on whether the day is past or future).
        """
        today = pd.Timestamp.today().normalize()
        month_str = today.strftime("%Y-%m")
        month_start = today.replace(day=1)
        days_in_month = int(today.days_in_month)
        day_of_month = int(today.day)
        days_remaining = days_in_month - day_of_month

        # --- Trend baselines (complete months only) ---
        monthly_exp = self.get_monthly_expenses(exclude_pending_refunds=True)
        avg_monthly_expenses = monthly_exp.get("avg_3_months", 0.0) or 0.0
        if avg_monthly_expenses <= 0:
            avg_monthly_expenses = (
                monthly_exp.get("avg_6_months", 0.0)
                or monthly_exp.get("avg_12_months", 0.0)
                or 0.0
            )

        ie_over_time = self.get_income_expenses_over_time()
        complete_months = [m for m in ie_over_time if m["month"] < month_str]
        recent = complete_months[-3:] if len(complete_months) >= 3 else complete_months
        avg_monthly_income = (
            sum(m["income"] for m in recent) / len(recent) if recent else 0.0
        )

        # --- Month-to-date actuals (non-CC cashflow) ---
        df = self.repo.get_cashflow_transactions()
        actual_income = 0.0
        actual_expenses = 0.0
        per_day_net: dict[int, float] = {}
        if not df.empty:
            df = df.copy()
            df["date_parsed"] = pd.to_datetime(df["date"])
            mtd = df[(df["date_parsed"] >= month_start) & (df["date_parsed"] <= today)]
            if not mtd.empty:
                actual_income, _, actual_expenses = self.get_income_investments_and_expenses(mtd)
                per_day_net = (
                    mtd.groupby(mtd["date_parsed"].dt.day)["amount"].sum().to_dict()
                )

        # --- Current bank balance ---
        balances = self.bank_balance_service.get_all_balances()
        current_bank_balance = float(sum(b["balance"] for b in balances)) if balances else 0.0

        # --- Projection ---
        trend_daily_expense = avg_monthly_expenses / days_in_month if days_in_month else 0.0
        projected_remaining_expenses = max(0.0, trend_daily_expense * days_remaining)
        expected_expenses = actual_expenses + projected_remaining_expenses
        expected_income = max(actual_income, avg_monthly_income)
        projected_remaining_income = max(0.0, expected_income - actual_income)
        projected_net = expected_income - expected_expenses
        projected_end_balance = (
            current_bank_balance + projected_remaining_income - projected_remaining_expenses
        )

        # --- Known upcoming recurring charges still due this month ---
        # Detected subscriptions/bills whose next expected charge falls in the
        # remainder of the month. Subtracted from "safe to spend" so the figure
        # reflects money still earmarked for committed bills, not just income
        # minus what's been spent so far.
        from backend.services.recurring_service import RecurringService

        month_end = today + pd.offsets.MonthEnd(0)
        committed_remaining = 0.0
        for item in RecurringService(self.db).get_recurring()["items"]:
            if item["status"] == "ended":
                continue
            next_due = pd.Timestamp(item["next_expected_date"])
            if today < next_due <= month_end:
                committed_remaining += item["amount"]

        safe_to_spend = max(0.0, expected_income - actual_expenses - committed_remaining)
        safe_to_spend_daily = (
            safe_to_spend / days_remaining if days_remaining > 0 else safe_to_spend
        )

        # --- Daily trajectory for the chart ---
        month_start_balance = current_bank_balance - (actual_income - actual_expenses)
        remaining_daily_net = (
            (projected_remaining_income - projected_remaining_expenses) / days_remaining
            if days_remaining > 0
            else 0.0
        )
        daily = []
        cumulative = 0.0
        last_actual_balance = month_start_balance
        for d in range(1, days_in_month + 1):
            date_str = month_start.replace(day=d).strftime("%Y-%m-%d")
            if d <= day_of_month:
                cumulative += float(per_day_net.get(d, 0.0))
                bal = month_start_balance + cumulative
                last_actual_balance = bal
                daily.append({
                    "date": date_str,
                    "actual_balance": round(bal, 2),
                    # anchor the projected line to today so the two segments join
                    "projected_balance": round(bal, 2) if d == day_of_month else None,
                })
            else:
                proj = last_actual_balance + remaining_daily_net * (d - day_of_month)
                daily.append({
                    "date": date_str,
                    "actual_balance": None,
                    "projected_balance": round(proj, 2),
                })

        return {
            "month": month_str,
            "days_in_month": days_in_month,
            "day_of_month": day_of_month,
            "days_remaining": days_remaining,
            "actual_income": round(actual_income, 2),
            "actual_expenses": round(actual_expenses, 2),
            "expected_income": round(expected_income, 2),
            "expected_expenses": round(expected_expenses, 2),
            "projected_net": round(projected_net, 2),
            "current_bank_balance": round(current_bank_balance, 2),
            "projected_end_balance": round(projected_end_balance, 2),
            "safe_to_spend": round(safe_to_spend, 2),
            "safe_to_spend_daily": round(safe_to_spend_daily, 2),
            "avg_monthly_income": round(avg_monthly_income, 2),
            "avg_monthly_expenses": round(avg_monthly_expenses, 2),
            "committed_remaining": round(committed_remaining, 2),
            "daily": daily,
        }

    def get_monthly_expenses(
        self,
        exclude_pending_refunds: bool = True,
        include_projects: bool = False,
    ) -> dict:
        """
        Get monthly expense totals and rolling averages, calculated like the monthly budget.

        Delegates filtering to ``MonthlyBudgetService.get_filtered_expenses``
        so that category exclusions, project exclusions, pending-refund
        handling, and split-parent removal are always consistent with
        the budget view.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            When ``True``, excludes transactions marked as pending refunds.
            Default is ``True``.
        include_projects : bool, optional
            When ``True``, includes project expenses as a separate
            ``project_expenses`` field per month. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``months`` -- list of ``{month, expenses, project_expenses?}`` dicts.
            - ``avg_3_months`` -- average monthly expenses over the last 3 months.
            - ``avg_6_months`` -- average monthly expenses over the last 6 months.
            - ``avg_12_months`` -- average monthly expenses over the last 12 months.
        """
        from backend.services.budget_service import (
            MonthlyBudgetService,
            ProjectBudgetService,
        )

        empty_result = {
            "months": [],
            "avg_3_months": 0.0,
            "avg_6_months": 0.0,
            "avg_12_months": 0.0,
        }

        budget_service = MonthlyBudgetService(self.db)
        expenses = budget_service.get_filtered_expenses(
            exclude_pending_refunds=exclude_pending_refunds,
        )

        if expenses.empty:
            return empty_result

        # Group by month and sum (amounts are negative, multiply by -1)
        expenses = expenses.copy()
        expenses["month"] = expenses[
            TransactionsTableFields.DATE.value
        ].dt.strftime("%Y-%m")

        monthly = (
            expenses.groupby("month")[TransactionsTableFields.AMOUNT.value]
            .sum()
            .mul(-1)
            .sort_index()
        )

        # Optionally compute project expenses per month
        monthly_project: pd.Series | None = None
        if include_projects:
            project_service = ProjectBudgetService(self.db)
            project_names = project_service.get_all_projects_names()
            if project_names:
                all_data = budget_service.transactions_service.get_data_for_analysis()
                project_txns = all_data.loc[
                    (~all_data[TransactionsTableFields.TYPE.value].isin(["split_parent"]))
                    & all_data[TransactionsTableFields.CATEGORY.value].isin(project_names)
                ].copy()
                if not project_txns.empty:
                    project_txns[TransactionsTableFields.DATE.value] = pd.to_datetime(
                        project_txns[TransactionsTableFields.DATE.value]
                    )
                    project_txns["month"] = project_txns[
                        TransactionsTableFields.DATE.value
                    ].dt.strftime("%Y-%m")
                    monthly_project = (
                        project_txns.groupby("month")[TransactionsTableFields.AMOUNT.value]
                        .sum()
                        .mul(-1)
                    )

        # Build months list
        all_months = sorted(set(monthly.index) | (set(monthly_project.index) if monthly_project is not None else set()))
        months_list = []
        for month in all_months:
            entry: dict = {
                "month": month,
                "expenses": round(float(monthly.get(month, 0.0)), 2),
            }
            if include_projects:
                entry["project_expenses"] = round(
                    float(monthly_project.get(month, 0.0)) if monthly_project is not None else 0.0, 2
                )
            months_list.append(entry)

        # Calculate averages relative to current month
        today = pd.Timestamp.today()

        def avg_last_n_months(n: int) -> float:
            month_keys = [
                (today - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(n)
            ]
            total = sum(monthly.get(m, 0.0) for m in month_keys)
            if include_projects and monthly_project is not None:
                total += sum(monthly_project.get(m, 0.0) for m in month_keys)
            return round(float(total / n), 2)

        return {
            "months": months_list,
            "avg_3_months": avg_last_n_months(3),
            "avg_6_months": avg_last_n_months(6),
            "avg_12_months": avg_last_n_months(12),
        }
