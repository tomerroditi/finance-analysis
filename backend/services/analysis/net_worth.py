"""
Net-balance / net-worth trends.

Provides the ``NetWorthMixin`` with the cumulative net-balance series and
the monthly net-worth reconstruction (bank + investments + cash). Mixed into
``AnalysisService`` (see ``core.py``).
"""

from typing import Any

import pandas as pd

from backend.constants.tables import Tables
from backend.utils.dataframe_dates import to_month_series


class NetWorthMixin:
    """Net-balance and net-worth methods for ``AnalysisService``."""

    def get_net_balance_over_time(self) -> list[dict[str, Any]]:
        """
        Get monthly net balance and cumulative balance over time.

        Credit card transactions are excluded to avoid double-counting. The
        cumulative balance starts from the combined bank, investment and cash
        prior wealth, shown as an anchor entry one month before the earliest
        transaction.

        Returns
        -------
        list[dict[str, Any]]
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

        df["month"] = to_month_series(df["date"])
        cumulative = bank_prior_wealth + investment_prior_wealth + cash_prior_wealth

        trend = [
            {
                "month": (
                    pd.to_datetime(df["date"].min()) - pd.DateOffset(months=1)
                ).strftime("%Y-%m"),
                "net_change": 0.0,
                "cumulative_balance": round(cumulative, 2),
            }
        ]

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

    def get_net_worth_over_time(self) -> list[dict[str, Any]]:
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
        list[dict[str, Any]]
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
        df["month"] = to_month_series(df["date"])
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
        anchor_month = (
            pd.to_datetime(months[0] + "-01") - pd.DateOffset(months=1)
        ).strftime("%Y-%m")

        result = [
            {
                "month": anchor_month,
                "bank_balance": round(prior_wealth_total, 2),
                "investment_value": 0.0,
                "cash": round(cash_prior_wealth, 2),
                "net_worth": round(prior_wealth_total + cash_prior_wealth, 2),
            }
        ]

        # Value the portfolio at every month end in a single pass rather than
        # re-fetching every investment and its snapshots once per month.
        month_ends = {
            month: (pd.to_datetime(month + "-01") + pd.offsets.MonthEnd(0))
            for month in months
        }
        inv_values = self.investments_service.get_total_values_at_dates(
            [month_end.strftime("%Y-%m-%d") for month_end in month_ends.values()]
        )

        for month in months:
            month_end = month_ends[month]
            month_end_str = month_end.strftime("%Y-%m-%d")

            bank_balance = prior_wealth_total + float(
                bank_df.loc[bank_df["date_parsed"] <= month_end, "amount"].sum()
            )

            inv_value = inv_values[month_end_str]

            cash_balance = (
                cash_prior_wealth
                + float(
                    cash_df.loc[cash_df["date_parsed"] <= month_end, "amount"].sum()
                )
                if not cash_df.empty
                else cash_prior_wealth
            )

            result.append(
                {
                    "month": month,
                    "bank_balance": round(bank_balance, 2),
                    "investment_value": round(inv_value, 2),
                    "cash": round(cash_balance, 2),
                    "net_worth": round(bank_balance + inv_value + cash_balance, 2),
                }
            )

        return result
