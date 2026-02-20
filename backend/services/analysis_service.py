from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    IncomeCategories,
    LiabilitiesCategories,
    NonExpensesCategories,
)
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.investments_service import InvestmentsService


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionsRepository(db)
        self.balance_repo = BankBalanceRepository(db)
        self.investments_repo = InvestmentsRepository(db)
        self.investments_service = InvestmentsService(db)

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

        income, expenses = self.get_income_and_expenses(df)

        return {
            "latest_data_date": latest_date,
            "total_transactions": len(df),
            "total_income": income,
            "total_expenses": expenses,
            "net_balance_change": income - expenses,
        }

    def get_income_expenses_over_time(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        df = self.repo.get_table()
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

        monthly_data = []
        for month in sorted(df["month"].unique()):
            month_df = df[df["month"] == month]
            income, expenses = self.get_income_and_expenses(month_df)
            monthly_data.append(
                {
                    "month": month,
                    "income": income,
                    "expenses": expenses,
                }
            )

        return monthly_data

    def get_income_and_expenses(self, df: pd.DataFrame) -> tuple[float, float]:
        df = df[df["source"] != "credit_card_transactions"]
        income_mask = self._get_income_mask(df)
        income = float(df[income_mask]["amount"].sum())
        expenses = float(df[~income_mask]["amount"].sum()) * -1
        return income, expenses

    def _get_income_mask(self, df: pd.DataFrame) -> pd.Series:
        return df["category"].isin([c.value for c in IncomeCategories]) | (
            df["category"].isin([c.value for c in LiabilitiesCategories])
            & (df["amount"] > 0)
        )

    def _get_bank_prior_wealth_total(self) -> float:
        """Get total prior wealth from all bank balance records."""
        df = self.balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def _get_investment_prior_wealth_total(self) -> float:
        """Get total prior wealth from all open investments."""
        df = self.investments_repo.get_all_investments(include_closed=False)
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def get_net_balance_over_time(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> list[dict]:
        """
        Get monthly net balance and cumulative balance over time.
        """
        df = self.repo.get_table()
        df = df[df["source"] != "credit_card_transactions"]

        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        if df.empty:
            return []

        trend = []
        cumulative = 0.0

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
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
        txn_prior_wealth = other_income_df[
            other_income_df["tag"] == PRIOR_WEALTH_TAG
        ]["amount"].sum()
        bank_prior_wealth = self._get_bank_prior_wealth_total()
        investment_prior_wealth = self._get_investment_prior_wealth_total()
        sources[PRIOR_WEALTH_TAG] = txn_prior_wealth + bank_prior_wealth + investment_prior_wealth
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

    def get_net_worth_over_time(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> list[dict]:
        """
        Get monthly net worth (bank balance + investment value) over time.

        Bank balance is reconstructed as prior_wealth + cumulative bank transactions.
        Investment value is the cumulative net invested amount across all investments.
        """
        df = self.repo.get_table()
        df = df[df["source"] != "credit_card_transactions"]

        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        if df.empty:
            return []

        prior_wealth = self._get_bank_prior_wealth_total() + self._get_investment_prior_wealth_total()

        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        months = sorted(df["month"].unique())

        full_df = self.repo.get_table()
        full_df = full_df[full_df["source"] != "credit_card_transactions"]
        full_df["date_parsed"] = pd.to_datetime(full_df["date"])

        result = []
        for month in months:
            month_end = pd.to_datetime(month + "-01") + pd.offsets.MonthEnd(0)
            month_end_str = month_end.strftime("%Y-%m-%d")

            bank_txns_to_date = full_df[full_df["date_parsed"] <= month_end]
            bank_balance = prior_wealth + float(bank_txns_to_date["amount"].sum())

            investment_value = self.investments_service.get_total_value_at_date(month_end_str)

            result.append({
                "month": month,
                "bank_balance": round(bank_balance, 2),
                "investment_value": round(investment_value, 2),
                "net_worth": round(bank_balance + investment_value, 2),
            })

        return result
