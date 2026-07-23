"""
Valuation and profit/loss calculations for the investments service.

Provides the ``ValuationMixin`` with balance resolution (snapshot-first,
transaction-based fallback), balance-over-time sampling, profit/loss
metrics, portfolio aggregations, and the shared transaction-fetch helpers.
Mixed into ``InvestmentsService`` (see ``core.py``).
"""

from bisect import bisect_right
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import select

from backend.models.transaction import InsuranceTransaction


class ValuationMixin:
    """Valuation and profit/loss methods for ``InvestmentsService``."""

    def calculate_current_balance(self, investment_id: int) -> float:
        """Calculate the current balance for an investment.

        Uses the latest balance snapshot if available, otherwise falls back
        to the transaction-based calculation ``-(sum of amounts)``.
        Returns ``0.0`` for closed investments.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        float
            Current balance.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return 0.0

        inv = investment.iloc[0]

        if inv["is_closed"]:
            return 0.0

        # Try snapshot first
        latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
            investment_id, date.today().strftime("%Y-%m-%d")
        )
        if latest is not None:
            return float(latest["balance"])

        # Fall back to transaction-based
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=investment_id
        )
        return self._calculate_balance_from_transactions(transactions_df)

    def get_total_value_at_date(self, target_date: str) -> float:
        """Sum snapshot-resolved balances for every investment as of a date.

        Per investment, applies the same resolution as
        ``calculate_current_balance``: latest snapshot on or before
        ``target_date`` if present, otherwise the transaction-based
        ``-sum(amounts up to target_date)``. Closed investments are
        included — they auto-receive a 0-balance snapshot at close, so
        the snapshot-first logic naturally returns 0 for dates after
        the close, and their pre-close value for dates before.

        Parameters
        ----------
        target_date : str
            Cut-off date in ``YYYY-MM-DD`` format (inclusive).

        Returns
        -------
        float
            Total portfolio value as of ``target_date``.
        """
        return self.get_total_values_at_dates([target_date])[target_date]

    def get_total_values_at_dates(self, target_dates: List[str]) -> Dict[str, float]:
        """Snapshot-resolved total portfolio value at many dates in one pass.

        Equivalent to calling :meth:`get_total_value_at_date` for each date,
        but fetches every investment's snapshots and transactions **once**
        instead of once per date. This turns the net-worth-over-time chart
        (which values the portfolio at each month end) from an O(months ×
        investments) database walk into O(investments) — the per-month
        resolution then happens in-memory.

        Per investment and per date the resolution is identical to the
        single-date method: the latest snapshot on or before the date if one
        exists (snapshots are unique per ``(investment, date)`` and stored as
        ``YYYY-MM-DD`` strings, so an ordered lexical search is exact),
        otherwise the transaction-based ``-sum(amounts up to the date)``.

        Parameters
        ----------
        target_dates : list[str]
            Cut-off dates in ``YYYY-MM-DD`` format (inclusive).

        Returns
        -------
        dict[str, float]
            Mapping of each requested date to the total portfolio value as of
            that date.
        """
        totals = {d: 0.0 for d in target_dates}
        if not target_dates:
            return totals

        investments = self.investments_repo.get_all_investments(include_closed=True)
        if investments.empty:
            return totals

        for _, inv in investments.iterrows():
            inv_id = int(inv["id"])
            snapshots = self.snapshots_repo.get_snapshots_for_investment(inv_id)
            snapshot_dates = snapshots["date"].tolist() if not snapshots.empty else []
            snapshot_balances = (
                snapshots["balance"].tolist() if not snapshots.empty else []
            )

            # Transactions are only needed for dates with no preceding
            # snapshot; fetch lazily so investments fully covered by snapshots
            # never touch the transactions table.
            txns = None
            for target_date in target_dates:
                idx = bisect_right(snapshot_dates, target_date) - 1
                if idx >= 0:
                    totals[target_date] += float(snapshot_balances[idx])
                    continue
                if txns is None:
                    txns = self._get_all_transactions_for_investment(
                        inv["category"], inv["tag"], investment_id=inv_id
                    )
                totals[target_date] += self._calculate_balance_from_transactions(
                    txns, as_of_date=target_date
                )
        return totals

    def calculate_balance_over_time(
        self, investment_id: int, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Calculate balance over time at the dates that actually move the line.

        Samples at month-starts plus the meaningful inflection points
        (start, end, snapshot dates, transaction dates). Daily resolution
        was wasteful: snapshots are monthly to begin with, the chart cannot
        display higher resolution than its pixel width, and both downstream
        callers (``get_portfolio_overview`` and ``get_portfolio_balance_history``)
        immediately decimate the output.

        When balance snapshots exist, interpolates linearly between snapshot
        points. Falls back to the transaction-based approach for dates before
        the first snapshot or when no snapshots exist.

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
            List of ``{"date": str, "balance": float}`` dicts, sorted by date.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return []

        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=investment_id
        )

        snapshots_df = self.snapshots_repo.get_snapshots_for_investment(investment_id)

        if transactions_df.empty and snapshots_df.empty:
            return []

        # For closed investments, stop at the last transaction date
        actual_end_date = end_date
        if inv["is_closed"] and not transactions_df.empty:
            last_txn_date = pd.to_datetime(transactions_df["date"]).max().date()
            requested_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            actual_end_date = min(last_txn_date, requested_end_date).strftime("%Y-%m-%d")

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(actual_end_date)
        sample_dates = pd.DatetimeIndex([start_ts, end_ts]).union(
            pd.date_range(start=start_ts, end=end_ts, freq="MS")
        )
        if not transactions_df.empty:
            txn_dates = pd.to_datetime(transactions_df["date"])
            sample_dates = sample_dates.union(
                txn_dates[(txn_dates >= start_ts) & (txn_dates <= end_ts)]
            )
        if not snapshots_df.empty:
            snap_dates = pd.to_datetime(snapshots_df["date"])
            sample_dates = sample_dates.union(
                snap_dates[(snap_dates >= start_ts) & (snap_dates <= end_ts)]
            )

        if snapshots_df.empty:
            balances = [
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "balance": self._calculate_balance_from_transactions(
                        transactions_df, as_of_date=d.strftime("%Y-%m-%d")
                    ),
                }
                for d in sample_dates
            ]
        else:
            snapshots_df = snapshots_df.copy()
            snapshots_df["date"] = pd.to_datetime(snapshots_df["date"])
            snapshots_df = snapshots_df.sort_values("date")

            balances = []
            for d in sample_dates:
                d_str = d.strftime("%Y-%m-%d")
                before = snapshots_df[snapshots_df["date"] <= d]
                after = snapshots_df[snapshots_df["date"] >= d]

                if not before.empty and not after.empty:
                    prev = before.iloc[-1]
                    nxt = after.iloc[0]

                    if prev["date"] == nxt["date"]:
                        balance = float(prev["balance"])
                    else:
                        total_days = (nxt["date"] - prev["date"]).days
                        elapsed_days = (d - prev["date"]).days
                        frac = elapsed_days / total_days if total_days > 0 else 0
                        balance = float(prev["balance"]) + frac * (
                            float(nxt["balance"]) - float(prev["balance"])
                        )
                elif not before.empty:
                    balance = float(before.iloc[-1]["balance"])
                else:
                    balance = self._calculate_balance_from_transactions(
                        transactions_df, as_of_date=d_str
                    )

                balances.append({"date": d_str, "balance": balance})

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
            inv["category"], inv["tag"], investment_id=investment_id
        )

        if transactions_df.empty:
            # No transactions — check if there's a snapshot (e.g. insurance-synced)
            if not inv["is_closed"]:
                latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                    investment_id, date.today().strftime("%Y-%m-%d")
                )
                if latest is not None:
                    balance = float(latest["balance"])
                    return {
                        "total_deposits": 0.0,
                        "total_withdrawals": 0.0,
                        "net_invested": 0.0,
                        "current_balance": balance,
                        "absolute_profit_loss": balance,
                        "roi_percentage": 0.0,
                        "total_years": 0.0,
                        "cagr_percentage": 0.0,
                        "first_transaction_date": None,
                    }
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
            # Try snapshot first, fall back to transaction-based
            latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                investment_id, date.today().strftime("%Y-%m-%d")
            )
            if latest is not None:
                current_balance = float(latest["balance"])
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

    def _build_allocation_entry(
        self, inv_id: int, inv_name: str, inv_type: str
    ) -> Dict[str, Any]:
        """Build a single allocation entry with metrics and sparkline history."""
        metrics = self.calculate_profit_loss(inv_id)

        start = metrics.get("first_transaction_date") or (
            date.today().replace(year=date.today().year - 1).strftime(r"%Y-%m-%d")
        )
        history = self.calculate_balance_over_time(
            inv_id, start, date.today().strftime(r"%Y-%m-%d")
        )
        if len(history) > 30:
            step = len(history) // 30
            condensed = history[::step]
            if history[-1] not in condensed:
                condensed.append(history[-1])
        else:
            condensed = history

        return {
            "id": inv_id,
            "name": inv_name,
            "balance": metrics["current_balance"],
            "type": inv_type,
            "profit_loss": metrics["absolute_profit_loss"],
            "roi": metrics["roi_percentage"],
            "total_deposits": metrics["total_deposits"],
            "total_withdrawals": metrics["total_withdrawals"],
            "cagr": metrics["cagr_percentage"],
            "history": [h["balance"] for h in condensed],
        }

    def get_portfolio_overview(self) -> Dict[str, Any]:
        """
        Get portfolio-level metrics and allocation data for all investments.

        Totals (total_value, total_profit, portfolio_roi) reflect open
        investments only.  The allocation list includes both open and closed
        investments so cards can be rendered from a single data source.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``total_value`` – sum of current balances across all open investments.
            - ``total_profit`` – total value minus net invested (deposits - withdrawals).
            - ``portfolio_roi`` – ``(total_value / total_deposits - 1) * 100`` percentage.
            - ``allocation`` – list of dicts per investment (open and closed).
        """
        all_investments = self.investments_repo.get_all_investments(include_closed=True)

        if all_investments.empty:
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

        # The merged analysis table each investment reads is memoized
        # per-session (see backend/utils/session_cache.py), so the loop
        # performs the full multi-table merge once, not ~2*N times.
        for _, inv in all_investments.iterrows():
            entry = self._build_allocation_entry(
                inv["id"], inv["name"], inv["type"]
            )
            allocation.append(entry)

            # Only open investments contribute to portfolio totals
            if not inv["is_closed"]:
                total_value += entry["balance"]
                total_deposits += entry["total_deposits"]
                total_withdrawals += entry["total_withdrawals"]

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

    def get_portfolio_balance_history(
        self, include_closed: bool = False
    ) -> Dict[str, Any]:
        """Get balance-over-time data for all investments, aligned by month.

        Parameters
        ----------
        include_closed : bool, optional
            When ``True``, closed investments are included. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``series`` – list of per-investment dicts with ``id``, ``name``,
              ``tag`` and ``data`` (list of ``{"date": str, "balance": float}``).
              ``id`` is the stable series key: investment names are not unique
              (e.g. several Keren Hishtalmut accounts share one name), so
              consumers must key by ``id`` and use ``name``/``tag`` for display
              only.
            - ``total`` – aggregated balance across all investments per month.
        """
        investments = self.investments_repo.get_all_investments(
            include_closed=include_closed
        )
        if investments.empty:
            return {"series": [], "total": []}

        all_series = []
        for _, inv in investments.iterrows():
            metrics = self.calculate_profit_loss(inv["id"])
            start = metrics.get("first_transaction_date") or (
                date.today().replace(year=date.today().year - 1).strftime(r"%Y-%m-%d")
            )
            history = self.calculate_balance_over_time(
                inv["id"], start, date.today().strftime(r"%Y-%m-%d")
            )
            if not history:
                continue

            # Downsample to monthly (first of each month + last point)
            df = pd.DataFrame(history)
            df["date"] = pd.to_datetime(df["date"])
            monthly = df.groupby(df["date"].dt.to_period("M")).last().reset_index(drop=True)
            monthly["date"] = monthly["date"].dt.strftime("%Y-%m-%d")

            all_series.append(
                {
                    "id": int(inv["id"]),
                    "name": inv["name"],
                    "tag": inv["tag"],
                    "data": monthly.to_dict(orient="records"),
                }
            )

        # Build total line aligned across all dates
        all_dates: set = set()
        for s in all_series:
            for point in s["data"]:
                all_dates.add(point["date"])
        sorted_dates = sorted(all_dates)

        total = []
        for d in sorted_dates:
            balance_sum = 0.0
            for s in all_series:
                # Find latest point on or before this date for this series
                latest_balance = 0.0
                for point in s["data"]:
                    if point["date"] <= d:
                        latest_balance = point["balance"]
                total_balance = latest_balance
                balance_sum += total_balance
            total.append({"date": d, "balance": balance_sum})

        return {"series": all_series, "total": total}

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
            txns = self._get_all_transactions_for_investment(inv["category"], inv["tag"], investment_id=int(inv["id"]))
            if not txns.empty:
                frames.append(txns)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined["date_parsed"] = pd.to_datetime(combined["date"])
        combined["amount"] = pd.to_numeric(combined["amount"], errors="coerce").fillna(0.0)
        return combined

    def _get_all_transactions_for_investment(
        self, category: str, tag: str, investment_id: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch all transactions for a given investment identified by category and tag.

        For insurance-linked investments, also includes insurance deposit
        transactions (with amounts negated to match the investment convention:
        negative = deposit).

        Parameters
        ----------
        category : str
            Investment category (e.g. ``"Investments"``).
        tag : str
            Investment tag identifying the specific instrument.
        investment_id : int, optional
            Investment ID used to look up insurance linkage.

        Returns
        -------
        pd.DataFrame
            Matching transactions from the merged analysis table.
        """
        manual_txns = self.transactions_service.get_transactions_by_tag(category, tag)

        if investment_id is None:
            return manual_txns

        inv_df = self.investments_repo.get_by_id(investment_id)
        policy_id = inv_df.iloc[0].get("insurance_policy_id")
        if not policy_id or pd.isna(policy_id):
            return manual_txns

        stmt = select(InsuranceTransaction).where(
            InsuranceTransaction.account_number == policy_id
        )
        ins_txns = pd.read_sql(stmt, self.db.bind)

        if ins_txns.empty:
            return manual_txns

        # Negate amounts: insurance txns are positive (deposits received),
        # but investment convention is negative = deposit (money out)
        ins_txns["amount"] = -ins_txns["amount"]

        if manual_txns.empty:
            return ins_txns

        # Preserve manual_txns column order so downstream code sees a stable schema
        common_cols = [c for c in manual_txns.columns if c in ins_txns.columns]
        return pd.concat(
            [manual_txns[common_cols], ins_txns[common_cols]], ignore_index=True
        )

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
