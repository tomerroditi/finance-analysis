from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.naming_conventions import (
    PRIOR_WEALTH_TAG,
    IncomeCategories,
    LiabilitiesCategories,
    NonExpensesCategories,
)
from backend.repositories.transactions_repository import TransactionsRepository


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionsRepository(db)

    def get_overview(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        """
        Get a financial overview including totals and latest data date.
        """
        # Get latest dates (always base on all data for status check)
        df = self.repo.get_table()
        latest_date = df["date"].max()

        # Get transaction counts (optionally filtered)
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        return {
            "latest_data_date": latest_date,
            "total_transactions": len(df),
        }

    def _get_income_mask(self, df: pd.DataFrame) -> pd.Series:
        return df["category"].isin([c.value for c in IncomeCategories]) | (
            df["category"].isin([c.value for c in LiabilitiesCategories])
            & (df["amount"] > 0)
        )

    def _get_income_amount(self, df: pd.DataFrame) -> float:
        df = df[df["source"] != "credit_card_transactions"]
        return float(df[self._get_income_mask(df)]["amount"].sum())

    def _get_expenses_amount(self, df: pd.DataFrame) -> float:
        df = df[df["source"] != "credit_card_transactions"]
        return float(df[~self._get_income_mask(df)]["amount"].sum()) * -1

    def get_total_income(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        df = self.repo.get_table()
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        return self._get_income_amount(df)

    def get_total_expenses(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        df = self.repo.get_table()
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        return self._get_expenses_amount(df)

    def get_expenses_by_category(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        """
        Get expenses grouped by category.
        """
        df = self.repo.get_table()

        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        if df.empty:
            return []

        expense_mask = ~df["category"].isin([c.value for c in NonExpensesCategories])
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

    def get_net_balance_trend(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> list[dict]:
        """
        Get monthly net balance and cumulative balance over time.
        """
        df = self.repo.get_table()

        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        if df.empty:
            return []

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

        trend = []
        cumulative = 0.0

        for month in sorted(df["month"].unique()):
            group = df[df["month"] == month]

            income = self._get_income_amount(group)
            expenses = self._get_expenses_amount(group)

            net = float(income - expenses)
            cumulative += net

            trend.append(
                {
                    "month": month,
                    "income": round(income, 2),
                    "expenses": round(expenses, 2),
                    "net": round(net, 2),
                    "cumulative": round(cumulative, 2),
                }
            )

        return trend

    def get_sankey_data(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> dict:
        """
        Get data for Sankey diagram.
        """
        df = self.repo.get_table(include_split_parents=False)

        # Date Filtering
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        if df.empty:
            return {"nodes": [], "links": []}

        # --- Processing ---
        IGNORE = NonExpensesCategories.IGNORE.value
        SALARY = IncomeCategories.SALARY.value
        OTHER_INCOME = IncomeCategories.OTHER_INCOME.value
        LIABILITIES = LiabilitiesCategories.LIABILITIES.value
        INVESTMENTS = NonExpensesCategories.INVESTMENTS.value

        total_income_node = "Total Income"

        # Initialize Aggregates
        sources = {}  # name -> amount
        destinations = {}  # name -> amount
        helpers = {}  # name -> amount

        df = df[df["category"] != IGNORE]

        sources[SALARY] = df[df["category"] == SALARY]["amount"].sum()
        # Split out Prior Wealth from Other Income
        other_income_df = df[df["category"] == OTHER_INCOME]
        sources[PRIOR_WEALTH_TAG] = other_income_df[
            other_income_df["tag"] == PRIOR_WEALTH_TAG
        ]["amount"].sum()
        sources[OTHER_INCOME] = other_income_df[
            other_income_df["tag"] != PRIOR_WEALTH_TAG
        ]["amount"].sum()
        sources["Loans"] = df[(df["category"] == LIABILITIES) & (df["amount"] > 0)][
            "amount"
        ].sum()
        # sources["Investments Withdrawal"] = df[(df['category'] == INVESTMENTS) & (df['amount'] > 0)]['amount'].sum()

        destinations["Paid Debt"] = abs(
            df[(df["category"] == LIABILITIES) & (df["amount"] < 0)]["amount"].sum()
        )
        # destinations["Investments Deposit"] = abs(df[(df['category'] == INVESTMENTS) & (df['amount'] < 0)]['amount'].sum())

        exclude_cats = [SALARY, OTHER_INCOME, LIABILITIES, INVESTMENTS, IGNORE]
        expenses_df = df[~df["category"].isin(exclude_cats)]
        for cat, group in expenses_df.groupby("category"):
            net = group["amount"].sum()
            if net > 0:
                sources[f"Refunds: {cat}"] = net
            elif net < 0:
                destinations[cat] = abs(net)

        # TODO: we need to account for payments and allocations from filtered out data to correctly calculate it
        helpers["Debt To Be Paid"] = df[(df["category"] == LIABILITIES)]["amount"].sum()
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
