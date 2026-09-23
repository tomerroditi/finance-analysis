"""
Valuation and profit/loss calculations for the investments service.

Provides the ``ValuationMixin`` with balance resolution (snapshot-first,
transaction-based fallback), balance-over-time sampling, profit/loss
metrics, portfolio aggregations, and the shared transaction-fetch helpers.
Mixed into ``InvestmentsService`` (see ``core.py``).
"""

from bisect import bisect_right
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

#: One day as a numpy timedelta, for date arithmetic on datetime64 values.
_ONE_DAY = np.timedelta64(1, "D")

HISHTALMUT_TYPE = "hishtalmut"
"""Investment ``type`` marking a Keren Hishtalmut account.

Matches ``insurance_accounts.policy_type`` so scraped policies and
manually-created KH investments share one identity.
"""

CLOSED_SOURCE = "closed"
"""Snapshot ``source`` of the zero balance written when an investment closes."""

OPENING_BALANCE_COLUMN = "is_opening_balance"
"""Marks the synthetic opening-balance row of an insurance-linked investment.

A provider only exposes a window of recent deposits, so a policy that predates
that window holds money no scraped deposit explains. The row carries that money
as one deposit, dated just before the window, so the balance history is
continuous and the pre-window capital is cost basis rather than profit. It is a
deposit for valuation only: P&L reports it apart from ``total_deposits`` (which
must keep matching the provider's deposit list) and the per-date flows skip it.
"""


class ValuationMixin:
    """Valuation and profit/loss methods for ``InvestmentsService``."""

    def calculate_current_balance(self, investment_id: int) -> float:
        """Calculate the current balance for an investment.

        Uses the latest balance snapshot if available — carried forward by
        the transactions recorded after it (see
        :meth:`_carry_snapshot_forward`) — otherwise falls back to the
        transaction-based calculation ``-(sum of amounts)``.
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

        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=investment_id
        )
        latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
            investment_id, date.today().strftime("%Y-%m-%d")
        )
        if latest is not None:
            return self._carry_snapshot_forward(
                float(latest["balance"]), str(latest["date"]), transactions_df
            )
        return self._calculate_balance_from_transactions(transactions_df)

    def get_hishtalmut_total_balance(self) -> float | None:
        """Return the total current balance across open Keren Hishtalmut investments.

        Covers both scraped policies (auto-synced by ``InsuranceSyncMixin``)
        and manually-created KH investments, so the retirement projection can
        subtract exactly what it adds back as its KH bucket.

        Returns
        -------
        float or None
            Summed current balance, or ``None`` when no open KH investment
            carries a positive balance.
        """
        total = sum(
            self.calculate_current_balance(int(inv["id"]))
            for inv in self.get_all_investments()
            if inv.get("type") == HISHTALMUT_TYPE
        )
        return total if total > 0 else None

    def get_total_value_at_date(self, target_date: str) -> float:
        """Sum snapshot-resolved balances for every investment as of a date.

        Per investment, applies the same resolution as
        ``calculate_current_balance``: latest snapshot on or before
        ``target_date`` if present (plus the transactions recorded after
        it, up to ``target_date``), otherwise the transaction-based
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

    def get_total_values_at_dates(self, target_dates: list[str]) -> dict[str, float]:
        """Return the snapshot-resolved total portfolio value at many dates in one pass.

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
        carried forward by the transactions between the snapshot and the
        date; otherwise the transaction-based ``-sum(amounts up to the
        date)``.

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
        totals = dict.fromkeys(target_dates, 0.0)
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

            txns = self._get_all_transactions_for_investment(
                inv["category"], inv["tag"], investment_id=inv_id
            )
            # Index once per investment, not once per (investment, date):
            # re-parsing the date column per date cost the net-worth chart
            # ~370 full date parses for 8 investments over 46 months. Each
            # date is now a binary search into a running total.
            index = self._balance_index(txns)
            for target_date in target_dates:
                idx = bisect_right(snapshot_dates, target_date) - 1
                if idx >= 0:
                    totals[target_date] += float(
                        snapshot_balances[idx]
                    ) + self._balance_at(
                        index, target_date, after_date=str(snapshot_dates[idx])
                    )
                    continue
                totals[target_date] += self._balance_at(index, target_date)
        return totals

    @staticmethod
    def _balance_index(
        transactions_df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build a date-ordered running balance for point-in-time lookups.

        Parameters
        ----------
        transactions_df : pd.DataFrame
            One investment's transactions.

        Returns
        -------
        tuple of np.ndarray
            ``(dates, cumulative)`` — ``dates`` are ``YYYY-MM-DD`` strings in
            ascending order (which for that format is also chronological, the
            same property the snapshot lookup relies on) and ``cumulative[i]``
            is the balance implied by every transaction up to and including
            ``dates[i]``. Rows with an unparseable date are dropped — ``NaT``
            can never satisfy a cut-off.
        """
        empty = (np.array([], dtype="<U10"), np.array([], dtype=float))
        if transactions_df.empty or "amount" not in transactions_df.columns:
            return empty

        dates = pd.to_datetime(transactions_df["date"], errors="coerce")
        amounts = pd.to_numeric(transactions_df["amount"], errors="coerce").fillna(0.0)
        valid = dates.notna()
        if not valid.any():
            return empty
        dates, amounts = dates[valid], amounts[valid]

        order = np.argsort(dates.to_numpy(), kind="stable")
        # Balance is the negated sum: a deposit of -1000 adds 1000.
        return (
            dates.dt.strftime("%Y-%m-%d").to_numpy().astype("<U10")[order],
            np.cumsum(-amounts.to_numpy(dtype=float)[order]),
        )

    @staticmethod
    def _balance_at(
        index: tuple[np.ndarray, np.ndarray],
        as_of_date: str,
        after_date: str | None = None,
    ) -> float:
        """Read a balance out of a :meth:`_balance_index`.

        Parameters
        ----------
        index : tuple of np.ndarray
            As returned by :meth:`_balance_index`.
        as_of_date : str
            Cut-off date (inclusive) in ``YYYY-MM-DD`` format.
        after_date : str, optional
            When given, only transactions dated strictly after this date
            count — the snapshot carry-forward case, where anything on or
            before the snapshot is already inside its balance.

        Returns
        -------
        float
            The balance those transactions imply.
        """
        dates, cumulative = index
        if dates.size == 0:
            return 0.0

        end = int(np.searchsorted(dates, as_of_date, side="right"))
        total = float(cumulative[end - 1]) if end > 0 else 0.0
        if after_date is not None:
            start = int(np.searchsorted(dates, after_date, side="right"))
            total -= float(cumulative[start - 1]) if start > 0 else 0.0
        return total

    def calculate_balance_over_time(
        self, investment_id: int, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Calculate balance over time at the dates that actually move the line.

        Samples at month-starts plus the meaningful inflection points
        (start, end, snapshot dates, transaction dates). Daily resolution
        was wasteful: snapshots are monthly to begin with, the chart cannot
        display higher resolution than its pixel width, and both downstream
        callers (``get_portfolio_overview`` and ``get_portfolio_balance_history``)
        immediately decimate the output.

        When balance snapshots exist, interpolates linearly between snapshot
        points. Falls back to the transaction-based approach for dates before
        the first snapshot or when no snapshots exist. Past the newest
        snapshot the line is that snapshot carried forward by the
        transactions recorded after it (a deposit made after the last
        valuation raises the balance instead of vanishing until the next
        snapshot).

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
            actual_end_date = min(last_txn_date, requested_end_date).strftime(
                "%Y-%m-%d"
            )

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

        # Index the transactions once for the whole series rather than
        # re-parsing the date column per sample date — for the portfolio
        # overview (8 investments × ~39 samples) that was over 300 full date
        # parses for one request.
        index = self._balance_index(transactions_df)

        if snapshots_df.empty:
            balances = [
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "balance": self._balance_at(index, d.strftime("%Y-%m-%d")),
                }
                for d in sample_dates
            ]
        else:
            snapshots_df = snapshots_df.copy()
            snapshots_df["date"] = pd.to_datetime(snapshots_df["date"])
            snapshots_df = snapshots_df.sort_values("date")
            # Bracketing each sample date by binary search rather than two
            # boolean masks over the whole frame per date.
            snap_dates = snapshots_df["date"].to_numpy()
            snap_balances = snapshots_df["balance"].to_numpy(dtype=float)

            balances = []
            for d in sample_dates:
                d_str = d.strftime("%Y-%m-%d")
                d64 = d.to_datetime64()
                # Last snapshot on or before d, and first on or after it.
                prev_idx = int(np.searchsorted(snap_dates, d64, side="right")) - 1
                next_idx = int(np.searchsorted(snap_dates, d64, side="left"))

                has_prev = prev_idx >= 0
                has_next = next_idx < snap_dates.size

                if has_prev and has_next:
                    prev_date = snap_dates[prev_idx]
                    next_date = snap_dates[next_idx]
                    prev_balance = float(snap_balances[prev_idx])

                    if prev_date == next_date:
                        balance = prev_balance
                    else:
                        total_days = (next_date - prev_date) / _ONE_DAY
                        elapsed_days = (d64 - prev_date) / _ONE_DAY
                        frac = elapsed_days / total_days if total_days > 0 else 0
                        balance = prev_balance + frac * (
                            float(snap_balances[next_idx]) - prev_balance
                        )
                elif has_prev:
                    balance = float(snap_balances[prev_idx]) + self._balance_at(
                        index,
                        d_str,
                        after_date=pd.Timestamp(snap_dates[prev_idx]).strftime(
                            "%Y-%m-%d"
                        ),
                    )
                else:
                    balance = self._balance_at(index, d_str)

                balances.append({"date": d_str, "balance": balance})

        return balances

    def calculate_profit_loss(self, investment_id: int) -> dict[str, Any]:
        """
        Calculate comprehensive profit/loss metrics for an investment.

        For closed investments, ``current_balance`` is ``0.0`` and
        ``absolute_profit_loss`` is ``total_withdrawals`` minus the cost basis
        (deposits plus opening balance).

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``total_deposits`` – absolute sum of negative transaction amounts,
              excluding the opening balance.
            - ``total_withdrawals`` – sum of positive transaction amounts.
            - ``opening_balance`` – capital an insurance-linked investment held
              before its provider's deposit history (see
              ``OPENING_BALANCE_COLUMN``); ``0.0`` otherwise.
            - ``net_invested`` – deposits plus opening balance minus withdrawals.
            - ``current_balance`` – current reconstructed balance (0 if closed).
            - ``absolute_profit_loss`` – current balance minus net invested.
            - ``roi_percentage`` – ``(final_value / cost_basis - 1) * 100``, where
              ``cost_basis`` is deposits plus opening balance.
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
                        "opening_balance": 0.0,
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
                "opening_balance": 0.0,
                "net_invested": 0.0,
                "current_balance": 0.0,
                "absolute_profit_loss": 0.0,
                "roi_percentage": 0.0,
                "total_years": 0.0,
                "cagr_percentage": 0.0,
                "first_transaction_date": None,
            }

        if "amount" in transactions_df.columns:
            transactions_df["amount"] = pd.to_numeric(
                transactions_df["amount"], errors="coerce"
            ).fillna(0.0)

        opening_mask = self._opening_balance_mask(transactions_df)
        opening_balance = abs(float(transactions_df.loc[opening_mask, "amount"].sum()))
        flows = transactions_df[~opening_mask]
        # Transaction sign: Negative = deposit (money OUT), Positive = withdrawal (money IN)
        total_deposits = abs(flows[flows["amount"] < 0]["amount"].sum())
        total_withdrawals = flows[flows["amount"] > 0]["amount"].sum()
        cost_basis = total_deposits + opening_balance
        net_invested = cost_basis - total_withdrawals

        if inv["is_closed"]:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - cost_basis
        else:
            # Snapshot first (carried forward by later transactions), fall
            # back to transaction-based
            latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                investment_id, date.today().strftime("%Y-%m-%d")
            )
            if latest is not None:
                current_balance = self._carry_snapshot_forward(
                    float(latest["balance"]), str(latest["date"]), transactions_df
                )
            else:
                current_balance = self._calculate_balance_from_transactions(
                    transactions_df
                )
            absolute_profit_loss = current_balance - net_invested

        final_value = (
            total_withdrawals
            if inv["is_closed"]
            else current_balance + total_withdrawals
        )
        roi_percentage = (
            ((final_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0.0
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
        if cost_basis > 0 and total_years > 0 and final_value > 0:
            cagr_percentage = (
                (final_value / cost_basis) ** (1 / total_years) - 1
            ) * 100

        return {
            "total_deposits": float(total_deposits),
            "total_withdrawals": float(total_withdrawals),
            "opening_balance": opening_balance,
            "net_invested": float(net_invested),
            "current_balance": float(current_balance),
            "absolute_profit_loss": float(absolute_profit_loss),
            "roi_percentage": float(roi_percentage),
            "total_years": float(total_years),
            "cagr_percentage": float(cagr_percentage),
            "first_transaction_date": first_date.strftime("%Y-%m-%d"),
        }

    @staticmethod
    def _opening_balance_mask(transactions_df: pd.DataFrame) -> pd.Series:
        """Select the synthetic opening-balance row of a transactions frame.

        Parameters
        ----------
        transactions_df : pd.DataFrame
            Output of ``_get_all_transactions_for_investment``.

        Returns
        -------
        pd.Series
            Boolean mask, all ``False`` when the frame carries no opening row.
        """
        if OPENING_BALANCE_COLUMN not in transactions_df.columns:
            return pd.Series(False, index=transactions_df.index)
        return transactions_df[OPENING_BALANCE_COLUMN].fillna(False).astype(bool)

    @staticmethod
    def _default_history_start(metrics: dict[str, Any]) -> str:
        """Return the first transaction date, or one year ago when there is none."""
        return metrics.get("first_transaction_date") or (
            date.today().replace(year=date.today().year - 1).strftime(r"%Y-%m-%d")
        )

    def _build_allocation_entry(
        self, inv_id: int, inv_name: str, inv_type: str
    ) -> dict[str, Any]:
        """Build a single allocation entry with metrics and sparkline history."""
        metrics = self.calculate_profit_loss(inv_id)

        history = self.calculate_balance_over_time(
            inv_id,
            self._default_history_start(metrics),
            date.today().strftime(r"%Y-%m-%d"),
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
            "opening_balance": metrics["opening_balance"],
            "cagr": metrics["cagr_percentage"],
            "history": [h["balance"] for h in condensed],
        }

    def get_portfolio_overview(self) -> dict[str, Any]:
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
            - ``total_profit`` – total value minus net invested (deposits plus
              opening balances, minus withdrawals).
            - ``portfolio_roi`` – ``((total_value + total_withdrawals) / cost_basis - 1) * 100``
              percentage, where ``cost_basis`` is deposits plus opening balances —
              the per-investment ROI formula over the open investments, so money
              already withdrawn counts as returned rather than lost.
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
        cost_basis = 0.0
        total_withdrawals = 0.0
        allocation: list[dict[str, Any]] = []

        # The merged analysis table each investment reads is memoized
        # per-session (see backend/utils/session_cache.py), so the loop
        # performs the full multi-table merge once, not ~2*N times.
        for _, inv in all_investments.iterrows():
            entry = self._build_allocation_entry(inv["id"], inv["name"], inv["type"])
            allocation.append(entry)

            # Only open investments contribute to portfolio totals
            if not inv["is_closed"]:
                total_value += entry["balance"]
                cost_basis += entry["total_deposits"] + entry["opening_balance"]
                total_withdrawals += entry["total_withdrawals"]

        total_profit = total_value - (cost_basis - total_withdrawals)
        portfolio_roi = (
            ((total_value + total_withdrawals) / cost_basis - 1) * 100
            if cost_basis > 0
            else 0.0
        )

        return {
            "total_value": total_value,
            "total_profit": total_profit,
            "portfolio_roi": portfolio_roi,
            "allocation": allocation,
        }

    def get_portfolio_balance_history(
        self, include_closed: bool = False
    ) -> dict[str, Any]:
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

        all_series: list[dict[str, Any]] = []
        for _, inv in investments.iterrows():
            metrics = self.calculate_profit_loss(inv["id"])
            history = self.calculate_balance_over_time(
                inv["id"],
                self._default_history_start(metrics),
                date.today().strftime(r"%Y-%m-%d"),
            )
            if not history:
                continue

            # Downsample to one point per month: its last sample.
            df = pd.DataFrame(history)
            df["date"] = pd.to_datetime(df["date"])
            monthly = (
                df.groupby(df["date"].dt.to_period("M")).last().reset_index(drop=True)
            )
            monthly["date"] = monthly["date"].dt.strftime("%Y-%m-%d")

            all_series.append(
                {
                    "id": int(inv["id"]),
                    "name": inv["name"],
                    "tag": inv["tag"],
                    "data": monthly.to_dict(orient="records"),
                }
            )

        sorted_dates = sorted(
            {point["date"] for s in all_series for point in s["data"]}
        )

        total: list[dict[str, Any]] = []
        for d in sorted_dates:
            balance_sum = 0.0
            for s in all_series:
                # Each series contributes its latest point on or before ``d``.
                latest_balance = 0.0
                for point in s["data"]:
                    if point["date"] <= d:
                        latest_balance = point["balance"]
                balance_sum += latest_balance
            total.append({"date": d, "balance": balance_sum})

        return {"series": all_series, "total": total}

    def get_all_investment_transactions_combined(
        self, include_closed: bool = True
    ) -> pd.DataFrame:
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
        investments = self.investments_repo.get_all_investments(
            include_closed=include_closed
        )
        if investments.empty:
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for _, inv in investments.iterrows():
            txns = self._get_all_transactions_for_investment(
                inv["category"], inv["tag"], investment_id=int(inv["id"])
            )
            if not txns.empty:
                frames.append(txns)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined["date_parsed"] = pd.to_datetime(combined["date"])
        combined["amount"] = pd.to_numeric(combined["amount"], errors="coerce").fillna(
            0.0
        )
        return combined

    def _get_all_transactions_for_investment(
        self, category: str, tag: str, investment_id: int | None = None
    ) -> pd.DataFrame:
        """
        Fetch all transactions for a given investment identified by category and tag.

        For insurance-linked investments, also includes insurance deposit
        transactions (with amounts negated to match the investment convention:
        negative = deposit) and, when the first balance snapshot holds more
        than those deposits explain, a synthetic opening-balance row flagged
        by ``OPENING_BALANCE_COLUMN``.

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

        ins_txns = self.transactions_repo.insurance_repo.get_for_policy(policy_id)

        if ins_txns.empty:
            combined = manual_txns
        else:
            # Negate amounts: insurance txns are positive (deposits received),
            # but investment convention is negative = deposit (money out)
            ins_txns["amount"] = -ins_txns["amount"]
            if manual_txns.empty:
                combined = ins_txns
            else:
                # Preserve manual_txns column order so downstream code sees a
                # stable schema
                common_cols = [c for c in manual_txns.columns if c in ins_txns.columns]
                combined = pd.concat(
                    [manual_txns[common_cols], ins_txns[common_cols]],
                    ignore_index=True,
                )

        return self._with_opening_balance(investment_id, combined)

    def _with_opening_balance(
        self, investment_id: int, transactions_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Prepend the capital a provider's deposit window does not explain.

        The first observed snapshot is the only fact about the balance before
        the scrape began. Whatever it holds beyond the deposits recorded on or
        before its date was already in the policy before the provider's
        deposit history starts, so it becomes one deposit dated the day
        before the earliest known event (see ``OPENING_BALANCE_COLUMN``).
        Growth inside the window up to the first snapshot is folded into that
        figure too — the data cannot tell the two apart, and understating
        profit beats reporting prior capital as gains.

        Parameters
        ----------
        investment_id : int
            ID of an insurance-linked investment.
        transactions_df : pd.DataFrame
            Its manual and insurance transactions (may be empty).

        Returns
        -------
        pd.DataFrame
            ``transactions_df`` with an ``OPENING_BALANCE_COLUMN`` column, plus
            the opening row when the first snapshot exceeds the deposits.
        """
        snapshots = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        if not snapshots.empty:
            snapshots = snapshots[snapshots["source"] != CLOSED_SOURCE]
        if snapshots.empty:
            return transactions_df

        first = snapshots.sort_values("date").iloc[0]
        first_date = pd.Timestamp(str(first["date"]))
        start = first_date
        recorded = 0.0
        if not transactions_df.empty:
            dates = pd.to_datetime(transactions_df["date"])
            amounts = pd.to_numeric(transactions_df["amount"], errors="coerce").fillna(
                0.0
            )
            # Deposits are negative, so adding them leaves what they do not cover.
            recorded = float(amounts[dates <= first_date].sum())
            start = min(start, dates.min())
        opening = float(first["balance"]) + recorded
        if opening <= 0:
            return transactions_df

        opening_row = pd.DataFrame(
            [
                {
                    "date": (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    "amount": -opening,
                    OPENING_BALANCE_COLUMN: True,
                }
            ]
        )
        if transactions_df.empty:
            return opening_row
        flagged = transactions_df.assign(**{OPENING_BALANCE_COLUMN: False})
        return pd.concat([opening_row, flagged], ignore_index=True)

    def _carry_snapshot_forward(
        self,
        snapshot_balance: float,
        snapshot_date: str,
        transactions_df: pd.DataFrame,
        as_of_date: str | None = None,
    ) -> float:
        """Resolve a balance from a snapshot plus the transactions after it.

        A snapshot is an observation of the whole holding on its date, so
        transactions on or before that date are already inside it. Anything
        recorded strictly after the snapshot (and on or before
        ``as_of_date``) has not been observed yet and is added on top with
        the usual sign convention (a deposit of ``-1000`` adds ``1000``).

        Parameters
        ----------
        snapshot_balance : float
            Balance recorded by the snapshot.
        snapshot_date : str
            Snapshot date in ``YYYY-MM-DD`` format.
        transactions_df : pd.DataFrame
            All transactions of the investment.
        as_of_date : str, optional
            Cut-off date (inclusive) in ``YYYY-MM-DD`` format. Defaults to
            today.

        Returns
        -------
        float
            The carried-forward balance.
        """
        return snapshot_balance + self._calculate_balance_from_transactions(
            transactions_df, as_of_date=as_of_date, after_date=snapshot_date
        )

    def _calculate_balance_from_transactions(
        self,
        transactions_df: pd.DataFrame,
        as_of_date: str | None = None,
        after_date: str | None = None,
    ) -> float:
        """
        Calculate a balance as the negated sum of transaction amounts.

        Deposits are negative amounts (money leaving the account for the
        investment), so negating the sum yields a positive balance.

        Parameters
        ----------
        transactions_df : pd.DataFrame
            Transactions to sum.
        as_of_date : str, optional
            Include transactions dated on or before this ``YYYY-MM-DD`` date.
            Defaults to today.
        after_date : str, optional
            When given, only transactions dated strictly after this
            ``YYYY-MM-DD`` date are included.

        Returns
        -------
        float
            The balance those transactions imply.
        """
        cutoff = (
            datetime.today().date()
            if as_of_date is None
            else datetime.strptime(as_of_date, "%Y-%m-%d").date()
        )

        if transactions_df.empty:
            return 0.0

        transactions_df = transactions_df.copy()
        transactions_df["date"] = pd.to_datetime(transactions_df["date"])

        txn_dates = transactions_df["date"].dt.date
        mask = txn_dates <= cutoff
        if after_date is not None:
            mask &= txn_dates > datetime.strptime(after_date, "%Y-%m-%d").date()
        filtered_df = transactions_df.loc[mask]

        if filtered_df.empty:
            return 0.0

        if "amount" not in filtered_df.columns:
            return 0.0

        filtered_df.loc[:, "amount"] = pd.to_numeric(
            filtered_df.loc[:, "amount"], errors="coerce"
        ).fillna(0.0)

        # A -1000 deposit then a +200 withdrawal leaves -(-1000 + 200) = 800.
        return float(-filtered_df.loc[:, "amount"].sum())
