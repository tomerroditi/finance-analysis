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
from backend.repositories.transactions_repository import TransactionsRepository

# TransactionsService is imported lazily inside __init__ to avoid a
# module-level circular dependency (TransactionsService also lazy-imports
# InvestmentsService inside its create/delete methods).


class InvestmentsService:
    """
    Service for managing investments with business logic for balance calculations,
    profit/loss tracking, and investment lifecycle management.
    """

    def __init__(self, db: Session):
        """
        Initialize the investments service.

        ``TransactionsService`` is imported lazily to avoid a circular import:
        ``TransactionsService`` also lazy-imports ``InvestmentsService`` inside
        its ``create_transaction`` and ``delete_transaction`` methods.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.investments_repo = InvestmentsRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        from backend.services.transactions_service import TransactionsService

        self.transactions_service = TransactionsService(db)

    def get_all_investments(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        """
        Get all investments as a list of JSON-safe dicts.

        Parameters
        ----------
        include_closed : bool, optional
            When ``True``, closed investments are included. Default is ``False``.

        Returns
        -------
        list[dict]
            Investment records with ``NaN`` values replaced by ``None``.
        """
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        df = df.replace({np.nan: None})
        return df.to_dict(orient="records")

    def get_investment(self, investment_id: int) -> Dict[str, Any]:
        """
        Get a single investment by ID as a JSON-safe dict.

        Parameters
        ----------
        investment_id : int
            ID of the investment to retrieve.

        Returns
        -------
        dict
            Investment record with ``NaN`` values replaced by ``None``.
        """
        df = self.investments_repo.get_by_id(investment_id)
        df = df.replace({np.nan: None})
        return df.iloc[0].to_dict()

    def get_investment_analysis(
        self,
        investment_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed profit/loss metrics and balance history for an investment.

        Defaults ``start_date`` to the first transaction date (or one year ago)
        and ``end_date`` to today when not provided.

        Parameters
        ----------
        investment_id : int
            ID of the investment to analyse.
        start_date : str, optional
            ISO date string (``YYYY-MM-DD``) for the start of the balance history.
        end_date : str, optional
            ISO date string (``YYYY-MM-DD``) for the end of the balance history.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``metrics`` – profit/loss metrics dict (from ``calculate_profit_loss``).
            - ``history`` – list of daily balance dicts (from ``calculate_balance_over_time``).
        """
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
        """
        Create a new investment record.

        Parameters
        ----------
        **kwargs
            Field values forwarded to ``InvestmentsRepository.create_investment``.
        """
        self.investments_repo.create_investment(**kwargs)

    def update_investment(self, investment_id: int, **updates) -> None:
        """
        Update an investment record.

        Parameters
        ----------
        investment_id : int
            ID of the investment to update.
        **updates
            Field names and new values forwarded to the repository.
        """
        self.investments_repo.update_investment(investment_id, **updates)

    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """
        Mark an investment as closed.

        Parameters
        ----------
        investment_id : int
            ID of the investment to close.
        closed_date : str
            Closure date in ``YYYY-MM-DD`` format.
        """
        self.investments_repo.close_investment(investment_id, closed_date)

    def reopen_investment(self, investment_id: int) -> None:
        """
        Reopen a previously closed investment.

        Parameters
        ----------
        investment_id : int
            ID of the investment to reopen.
        """
        self.investments_repo.reopen_investment(investment_id)

    def delete_investment(self, investment_id: int) -> None:
        """
        Delete an investment record.

        Parameters
        ----------
        investment_id : int
            ID of the investment to delete.
        """
        self.investments_repo.delete_investment(investment_id)

    def recalculate_prior_wealth(self, investment_id: int) -> None:
        """
        Calculate and store prior_wealth_amount for an investment.

        Reads ManualInvestmentTransactions directly (bypassing get_data_for_analysis
        to avoid depending on synthetic prior-wealth rows) and stores
        -(sum of amounts) as prior_wealth_amount. Equivalent to
        BankBalanceService.recalculate_for_account for bank accounts.

        Parameters
        ----------
        investment_id : int
            ID of the investment to recalculate.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]
        all_inv_txns = self.transactions_repo.get_table("manual_investments")
        if all_inv_txns.empty:
            prior_wealth = 0.0
        else:
            mask = (all_inv_txns["category"] == inv["category"]) & (
                all_inv_txns["tag"] == inv["tag"]
            )
            inv_txns = all_inv_txns[mask]
            if inv_txns.empty:
                prior_wealth = 0.0
            else:
                amounts = pd.to_numeric(
                    inv_txns["amount"], errors="coerce"
                ).fillna(0.0)
                prior_wealth = -float(amounts.sum())
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
        df = self.investments_repo.get_all_investments(include_closed=True)
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def get_portfolio_overview(self) -> Dict[str, Any]:
        """
        Get portfolio-level metrics and allocation data for all open investments.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``total_value`` – sum of current balances across all open investments.
            - ``total_profit`` – total value minus net invested (deposits - withdrawals).
            - ``portfolio_roi`` – ``(total_value / total_deposits - 1) * 100`` percentage.
            - ``allocation`` – list of ``{"name": str, "balance": float, "type": str}``
              dicts per investment.
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
        Calculate the current balance for an investment from all its transactions.

        Returns ``0.0`` for closed investments.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        float
            Current balance (deposits negated, so positive deposits → positive balance).
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
        Calculate balance at daily intervals between two dates for charting.

        For closed investments, the date range is capped at the closed date.
        An extra ``{"date": closed_date, "balance": 0.0}`` point is appended
        to visualise the closure.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        start_date : str
            Start of the date range in ``YYYY-MM-DD`` format.
        end_date : str
            End of the date range in ``YYYY-MM-DD`` format.

        Returns
        -------
        list[dict]
            List of ``{"date": str, "balance": float}`` dicts, one per day.
            Empty if the investment has no transactions.
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
        Calculate comprehensive profit/loss metrics for an investment.

        For closed investments, ``current_balance`` is ``0.0`` and
        ``absolute_profit_loss`` is ``total_withdrawals - total_deposits``.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``total_deposits`` – absolute sum of negative transaction amounts.
            - ``total_withdrawals`` – sum of positive transaction amounts.
            - ``net_invested`` – deposits minus withdrawals.
            - ``current_balance`` – current reconstructed balance (0 if closed).
            - ``absolute_profit_loss`` – current balance minus net invested.
            - ``roi_percentage`` – ``(final_value / total_deposits - 1) * 100``.
            - ``total_years`` – years between first transaction and today/close date.
            - ``cagr_percentage`` – compound annual growth rate as a percentage.
            - ``first_transaction_date`` – date string of the first transaction.
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

    def get_all_investment_transactions_combined(self, include_closed: bool = True) -> pd.DataFrame:
        """
        Fetch transactions for all investments in a single combined DataFrame.

        Parameters
        ----------
        include_closed : bool
            Whether to include transactions for closed investments.

        Returns
        -------
        pd.DataFrame
            Combined transactions with a parsed ``date_parsed`` column and
            numeric ``amount``.  Empty DataFrame if no investments exist.
        """
        investments = self.investments_repo.get_all_investments(include_closed=include_closed)
        if investments.empty:
            return pd.DataFrame()

        frames = []
        for _, inv in investments.iterrows():
            txns = self._get_all_transactions_for_investment(inv["category"], inv["tag"])
            if not txns.empty:
                frames.append(txns)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined["date_parsed"] = pd.to_datetime(combined["date"])
        combined["amount"] = pd.to_numeric(combined["amount"], errors="coerce").fillna(0.0)
        return combined

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
        """
        Fetch all transactions for a given investment identified by category and tag.

        Parameters
        ----------
        category : str
            Investment category (e.g. ``"Investments"``).
        tag : str
            Investment tag identifying the specific instrument.

        Returns
        -------
        pd.DataFrame
            Matching transactions from the merged analysis table.
        """
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
