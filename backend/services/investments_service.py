"""
Investments service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for investment tracking and analysis.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.investments_repository import InvestmentsRepository
from backend.services.transactions_service import TransactionsService


class InvestmentsService:
    """
    Service for managing investments with business logic for balance calculations,
    profit/loss tracking, and investment lifecycle management.
    """

    def __init__(self, db: Session):
        self.db = db
        self.investments_repo = InvestmentsRepository(db)
        self.transactions_service = TransactionsService(db)

    def get_all_investments(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        """Get all investments as a list of JSON-safe dicts."""
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        df = df.replace({np.nan: None})
        return df.to_dict(orient="records")

    def get_investment(self, investment_id: int) -> Dict[str, Any]:
        """Get a single investment by ID as a JSON-safe dict."""
        df = self.investments_repo.get_by_id(investment_id)
        df = df.replace({np.nan: None})
        return df.iloc[0].to_dict()

    def get_investment_analysis(
        self,
        investment_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get detailed analysis for a specific investment with date defaults."""
        metrics = self.calculate_profit_loss(investment_id)
        if not start_date:
            start_date = metrics.get("first_transaction_date") or (
                date.today().replace(year=date.today().year - 1).strftime(r"%Y-%m-%d")
            )
        if not end_date:
            end_date = date.today().strftime(r"%Y-%m-%d")

        history = self.calculate_balance_over_time(investment_id, start_date, end_date)
        return {"metrics": metrics, "history": history}

    def create_investment(self, **kwargs) -> None:
        """Create a new investment."""
        self.investments_repo.create_investment(**kwargs)

    def update_investment(self, investment_id: int, **updates) -> None:
        """Update an investment."""
        self.investments_repo.update_investment(investment_id, **updates)

    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """Close an investment."""
        self.investments_repo.close_investment(investment_id, closed_date)

    def reopen_investment(self, investment_id: int) -> None:
        """Reopen a closed investment."""
        self.investments_repo.reopen_investment(investment_id)

    def delete_investment(self, investment_id: int) -> None:
        """Delete an investment."""
        self.investments_repo.delete_investment(investment_id)

    def recalculate_prior_wealth(self, investment_id: int) -> None:
        """
        Calculate and store prior_wealth_amount for an investment.

        Reads all ManualInvestmentTransactions for the investment and stores
        -(sum of amounts) as prior_wealth_amount. Equivalent to
        BankBalanceService.recalculate_for_account for bank accounts.

        Parameters
        ----------
        investment_id : int
            ID of the investment to recalculate.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )
        if transactions_df.empty:
            prior_wealth = 0.0
        else:
            if "amount" in transactions_df.columns:
                transactions_df["amount"] = pd.to_numeric(
                    transactions_df["amount"], errors="coerce"
                ).fillna(0.0)
            prior_wealth = -float(transactions_df["amount"].sum())
        self.investments_repo.update_prior_wealth(investment_id, prior_wealth)

    def recalculate_prior_wealth_by_tag(self, category: str, tag: str) -> None:
        """
        Look up investment by category and tag, then recalculate prior_wealth_amount.

        Parameters
        ----------
        category : str
            Investment category (e.g. "Investments").
        tag : str
            Investment tag identifying the specific investment.
        """
        inv_df = self.investments_repo.get_by_category_tag(category, tag)
        if inv_df.empty:
            return
        self.recalculate_prior_wealth(int(inv_df.iloc[0]["id"]))

    def get_total_prior_wealth(self) -> float:
        """
        Sum prior_wealth_amount across all open (non-closed) investments.

        Returns
        -------
        float
            Total prior wealth across open investments.
        """
        df = self.investments_repo.get_all_investments(include_closed=False)
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def get_portfolio_overview(self) -> Dict[str, Any]:
        """
        Get portfolio-level metrics and allocation data.
        """
        investments = self.investments_repo.get_all_investments(include_closed=False)

        if investments.empty:
            return {
                "total_value": 0.0,
                "total_profit": 0.0,
                "portfolio_roi": 0.0,
                "allocation": [],
            }

        total_value = 0.0
        total_deposits = 0.0
        total_withdrawals = 0.0
        allocation = []

        for _, inv in investments.iterrows():
            metrics = self.calculate_profit_loss(inv["id"])

            total_value += metrics["current_balance"]
            total_deposits += metrics["total_deposits"]
            total_withdrawals += metrics["total_withdrawals"]

            allocation.append(
                {
                    "name": inv["name"],
                    "balance": metrics["current_balance"],
                    "type": inv["type"],
                }
            )

        total_profit = total_value - (total_deposits - total_withdrawals)
        portfolio_roi = (
            ((total_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        )

        return {
            "total_value": total_value,
            "total_profit": total_profit,
            "portfolio_roi": portfolio_roi,
            "allocation": allocation,
        }

    def calculate_current_balance(self, investment_id: int) -> float:
        """
        Calculate current balance from ALL transaction sources.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return 0.0

        inv = investment.iloc[0]

        if inv["is_closed"]:
            return 0.0

        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )
        return self._calculate_balance_from_transactions(transactions_df)

    def calculate_balance_over_time(
        self, investment_id: int, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Calculate balance at daily intervals for charting.
        Returns a list of dicts suitable for JSON response.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return []

        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )

        if transactions_df.empty:
            return []

        # For closed investments, stop at closed_date
        actual_end_date = end_date
        if inv["is_closed"] and inv["closed_date"]:
            closed_date = datetime.strptime(inv["closed_date"], "%Y-%m-%d").date()
            requested_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            actual_end_date = min(closed_date, requested_end_date).strftime("%Y-%m-%d")

        dates = pd.date_range(start=start_date, end=actual_end_date, freq="D")

        balances = []
        for date in dates:
            balance = self._calculate_balance_from_transactions(
                transactions_df, as_of_date=date.strftime("%Y-%m-%d")
            )
            balances.append({"date": date.strftime("%Y-%m-%d"), "balance": balance})

        if inv["is_closed"] and inv["closed_date"]:
            balances.append({"date": inv["closed_date"], "balance": 0.0})

        return balances

    def calculate_profit_loss(self, investment_id: int) -> Dict[str, Any]:
        """
        Calculate comprehensive profit/loss metrics.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )

        if transactions_df.empty:
            return {
                "total_deposits": 0.0,
                "total_withdrawals": 0.0,
                "net_invested": 0.0,
                "current_balance": 0.0,
                "absolute_profit_loss": 0.0,
                "roi_percentage": 0.0,
                "total_years": 0.0,
                "cagr_percentage": 0.0,
                "first_transaction_date": None,
            }

        # Ensure numeric type for amount
        if "amount" in transactions_df.columns:
            transactions_df["amount"] = pd.to_numeric(
                transactions_df["amount"], errors="coerce"
            ).fillna(0.0)

        # Transaction sign: Negative = deposit (money OUT), Positive = withdrawal (money IN)
        total_deposits = abs(
            transactions_df[transactions_df["amount"] < 0]["amount"].sum()
        )
        total_withdrawals = transactions_df[transactions_df["amount"] > 0][
            "amount"
        ].sum()
        net_invested = total_deposits - total_withdrawals

        if inv["is_closed"]:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - total_deposits
        else:
            current_balance = self._calculate_balance_from_transactions(transactions_df)
            absolute_profit_loss = current_balance - net_invested

        final_value = (
            total_withdrawals
            if inv["is_closed"]
            else current_balance + total_withdrawals
        )
        roi_percentage = (
            ((final_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        )

        transactions_df = transactions_df.copy()
        transactions_df["date"] = pd.to_datetime(transactions_df["date"])
        first_date = transactions_df["date"].min().date()
        last_date = datetime.today().date()
        if inv["is_closed"] and inv["closed_date"]:
            last_date = datetime.strptime(inv["closed_date"], "%Y-%m-%d").date()
        total_years = max(
            (last_date - first_date).days / 365.25, 0.01
        )  # Avoid division by zero

        cagr_percentage = 0.0
        if total_deposits > 0 and total_years > 0 and final_value > 0:
            cagr_percentage = (
                (final_value / total_deposits) ** (1 / total_years) - 1
            ) * 100

        return {
            "total_deposits": float(total_deposits),
            "total_withdrawals": float(total_withdrawals),
            "net_invested": float(net_invested),
            "current_balance": float(current_balance),
            "absolute_profit_loss": float(absolute_profit_loss),
            "roi_percentage": float(roi_percentage),
            "total_years": float(total_years),
            "cagr_percentage": float(cagr_percentage),
            "first_transaction_date": first_date.strftime("%Y-%m-%d"),
        }

    def get_total_value_at_date(self, as_of_date: str) -> float:
        """
        Get total portfolio value across all investments at a given date.

        Parameters
        ----------
        as_of_date : str
            Date in YYYY-MM-DD format.

        Returns
        -------
        float
            Sum of all investment balances as of the given date.
        """
        investments = self.investments_repo.get_all_investments(include_closed=True)
        if investments.empty:
            return 0.0

        total = 0.0
        for _, inv in investments.iterrows():
            txns = self._get_all_transactions_for_investment(inv["category"], inv["tag"])
            total += self._calculate_balance_from_transactions(txns, as_of_date=as_of_date)
        return total

    def _get_all_transactions_for_investment(
        self, category: str, tag: str
    ) -> pd.DataFrame:
        """Fetch ALL transactions for given category/tag."""
        return self.transactions_service.get_transactions_by_tag(category, tag)

    def _calculate_balance_from_transactions(
        self, transactions_df: pd.DataFrame, as_of_date: Optional[str] = None
    ) -> float:
        """
        Calculate balance from transactions.
        Deposits are negative amounts (money leaving account to investment),
        so we negate them to get positive balance.
        """
        if as_of_date is None:
            as_of_date = datetime.today().date()
        else:
            as_of_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()

        if transactions_df.empty:
            return 0.0

        transactions_df = transactions_df.copy()
        transactions_df["date"] = pd.to_datetime(transactions_df["date"])

        filtered_df = transactions_df.loc[transactions_df["date"].dt.date <= as_of_date]

        if filtered_df.empty:
            return 0.0

        if "amount" not in filtered_df.columns:
            return 0.0

        filtered_df.loc[:, "amount"] = pd.to_numeric(
            filtered_df.loc[:, "amount"], errors="coerce"
        ).fillna(0.0)

        # Balance = -(sum of all transactions)
        # If I deposited -1000, balance is +1000.
        # If I withdrew +200, balance is -(-1000 + 200) = -(-800) = 800.
        balance = -filtered_df.loc[:, "amount"].sum()

        return float(balance)
