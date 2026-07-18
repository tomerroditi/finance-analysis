"""
Net-balance / net-worth trends and the Sankey flow diagram.

Provides the ``NetWorthMixin`` with the cumulative net-balance series,
the monthly net-worth reconstruction (bank + investments + cash), and the
two-layer Sankey cash-flow data. Mixed into ``AnalysisService`` (see
``core.py``).
"""

import pandas as pd

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    CREDIT_CARDS,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)
from backend.constants.tables import Tables


class NetWorthMixin:
    """Net-balance, net-worth, and Sankey methods for ``AnalysisService``."""

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

        destinations["Paid Debt"] = abs(
            df[(df["category"] == LIABILITIES_CATEGORY) & (df["amount"] < 0)]["amount"].sum()
        )

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

        # Value the portfolio at every month end in a single pass rather than
        # one snapshot/transaction database walk per month (the old per-month
        # call re-fetched every investment and its snapshots for each month).
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
