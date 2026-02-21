import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    CREDIT_CARDS,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.investments_service import InvestmentsService
from backend.services.bank_balance_service import BankBalanceService


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
        latest_date = df["date"].max()

        income, investments, expenses = self.get_income_investments_and_expenses(df)
        income += self.bank_balance_service.get_total_prior_wealth() + self.investments_service.get_total_prior_wealth()

        # Add cash prior wealth to total income (same as bank/investment prior wealth)
        from backend.services.cash_balance_service import CashBalanceService
        cash_service = CashBalanceService(self.db)
        cash_prior_wealth = cash_service.get_total_prior_wealth()
        income += cash_prior_wealth

        return {
            "latest_data_date": latest_date,
            "total_income": income,
            "total_expenses": expenses,
            "total_investments": investments,
            "net_balance_change": income - expenses,
        }

    def get_income_expenses_over_time(self):
        """
        Aggregate income and expenses by month over time.

        Credit card transactions are excluded to avoid double-counting
        (bank debits already capture the net payment).

        Returns
        -------
        list[dict]
            Chronologically sorted list of monthly dicts with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``income`` – total income for the month.
            - ``expenses`` – total expenses for the month (absolute value).
        """
        df = self.repo.get_table()
        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

        monthly_data = []
        for month in sorted(df["month"].unique()):
            month_df = df[df["month"] == month]
            income, investments, expenses = self.get_income_investments_and_expenses(month_df)
            monthly_data.append(
                {
                    "month": month,
                    "income": income,
                    "investments": investments,
                    "expenses": expenses,
                }
            )

        return monthly_data

    def get_income_investments_and_expenses(
        self, df: pd.DataFrame
    ) -> tuple[float, float]:
        """
        Calculate total income, investments, and expenses from a transactions DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame (typically the full merged table).

        Returns
        -------
        tuple[float, float]
            A ``(income, expenses)`` pair where both values are non-negative.
            ``expenses`` is the absolute value of the sum of negative amounts.
        """
        df = df[df["source"] != "credit_card_transactions"]

        income_mask, investment_mask, expensses_mask = self.get_transactions_masks(df).values()

        income = float(df[income_mask]["amount"].sum())
        investments = float(df[investment_mask]["amount"].sum()) * -1
        expenses = float(df[expensses_mask]["amount"].sum()) * -1
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
        expensses_mask = ~income_mask & ~investment_mask

        return {
            "income": income_mask,
            "investments": investment_mask,
            "expenses": expensses_mask,
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

        df = self.repo.get_table(exclude_services=["credit_card_transactions"])

        if df.empty:
            return []
        
        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        cumulative = bank_prior_wealth + investment_prior_wealth


        trend = []
        trend .append(
            {
                "month": (pd.to_datetime(df["date"].min()) - pd.DateOffset(months=1)).strftime("%Y-%m"),
                "net_change": 0.0,
                "cumulative_balance": round(cumulative, 2),
            }
        )

        for month in sorted(df["month"].unique()):
            group = df[df["month"] == month]

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
        df = self.repo.get_table()

        if df.empty:
            return []

        exclude_categories = [INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY, CREDIT_CARDS, *IncomeCategories._value2member_map_.keys()]
        expense_mask = ~df["category"].isin(exclude_categories)
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
        df = self.repo.get_table(include_split_parents=False)

        if df.empty:
            return {"nodes": [], "links": []}

        # Calculate CC gap before filtering out Credit Cards category
        bank_cc_payments = abs(df[df["category"] == CREDIT_CARDS]["amount"].sum())
        itemized_cc_total = abs(df[df["source"] == "credit_card_transactions"]["amount"].sum())
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
        txn_prior_wealth = other_income_df[
            other_income_df["tag"] == PRIOR_WEALTH_TAG
        ]["amount"].sum()
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
        links: list[dict] = []

        def get_node_idx(name) -> int:
            if name not in nodes:
                nodes.append(name)
            return nodes.index(name)

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

        # Exclude credit card transactions (same as other income methods)
        df = df[df["source"] != "credit_card_transactions"]

        if df.empty:
            return []

        # Filter to income rows only
        income_mask = self._get_income_mask(df)
        income_df = df[income_mask].copy()

        # Exclude Prior Wealth transactions
        income_df = income_df[income_df["tag"] != PRIOR_WEALTH_TAG]

        if income_df.empty:
            return []

        # Build source labels
        income_df["source_label"] = income_df.apply(self._income_source_label, axis=1)

        income_df["month"] = pd.to_datetime(income_df["date"]).dt.strftime("%Y-%m")

        result = []
        for month in sorted(income_df["month"].unique()):
            month_df = income_df[income_df["month"] == month]
            sources = {}
            for label, group in month_df.groupby("source_label"):
                sources[label] = round(float(group["amount"].sum()), 2)
            total = round(sum(sources.values()), 2)
            result.append({"month": month, "sources": sources, "total": total})

        return result

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
            return "Loans"

        tag = row.get("tag")
        if pd.isna(tag) or tag is None or tag == "":
            return category
        return f"{category} / {tag}"

    def get_net_worth_over_time(self) -> list[dict]:
        """
        Get monthly net worth (bank balance + investment value) over time.

        Bank balance is reconstructed as ``prior_wealth + cumulative bank transactions``.
        Investment value is ``cumulative investment transactions``
        (negative investment amounts are deposits, so balance is negated sum).
        An anchor data point one month before the earliest transaction shows
        the pure prior-wealth baseline.

        Returns
        -------
        list[dict]
            List of monthly snapshots (anchor + one per month in range) with keys:

            - ``month`` – period in ``YYYY-MM`` format.
            - ``bank_balance`` – reconstructed bank balance at month end.
            - ``investment_value`` – reconstructed investment value at month end.
            - ``net_worth`` – ``bank_balance + investment_value``.
        """
        bank_prior_wealth = self.bank_balance_service.get_total_prior_wealth()
        investment_prior_wealth = self.investments_service.get_total_prior_wealth()
        prior_wealth_total = bank_prior_wealth + investment_prior_wealth

        # --- Bank transactions (all sources except credit card) ---
        df = self.repo.get_table(exclude_services=["credit_card_transactions"])

        if df.empty:
            return []

        df["date_parsed"] = pd.to_datetime(df["date"])
        df["month"] = df["date_parsed"].dt.strftime("%Y-%m")
        months = sorted(df["month"].unique())

        # --- Investment transactions: fetch once, filter per month in-memory ---
        inv_df = self.investments_service.get_all_investment_transactions_combined(include_closed=True)
        if not inv_df.empty:
            inv_df["date_parsed"] = pd.to_datetime(inv_df["date"])

        # --- Prior-wealth anchor point (1 month before earliest data) ---
        anchor_month = (pd.to_datetime(months[0] + "-01") - pd.DateOffset(months=1)).strftime("%Y-%m")

        result = [{
            "month": anchor_month,
            "bank_balance": round(prior_wealth_total, 2),
            "investment_value": 0.0,
            "net_worth": round(prior_wealth_total, 2),
        }]

        for month in months:
            month_end = pd.to_datetime(month + "-01") + pd.offsets.MonthEnd(0)

            bank_balance = prior_wealth_total + float(
                df.loc[df["date_parsed"] <= month_end, "amount"].sum()
            )

            inv_to_date = (
                -float(inv_df.loc[inv_df["date_parsed"] <= month_end, "amount"].sum())
                if not inv_df.empty else 0.0
            )

            result.append({
                "month": month,
                "bank_balance": round(bank_balance, 2),
                "investment_value": round(inv_to_date, 2),
                "net_worth": round(bank_balance + inv_to_date, 2),
            })

        return result
