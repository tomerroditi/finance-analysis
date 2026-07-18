"""
Analysis service — public API and dashboard overview.

Defines ``AnalysisService``, assembling the cash-flow (``cashflow.py``),
net-worth/Sankey (``net_worth.py``), and forecasting (``forecast.py``)
mixins around the dashboard overview aggregation.
"""

import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.analysis.cashflow import CashflowMixin
from backend.services.analysis.forecast import ForecastMixin
from backend.services.analysis.net_worth import NetWorthMixin
from backend.services.investments_service import InvestmentsService
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService


class AnalysisService(CashflowMixin, NetWorthMixin, ForecastMixin):
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
