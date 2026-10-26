"""
Valuation and profit/loss calculations for the investments service.

Provides the ``ValuationMixin`` with balance resolution (snapshot-first,
transaction-based fallback), balance-over-time sampling, profit/loss
metrics, portfolio aggregations, and the shared transaction-fetch helpers.
Mixed into ``InvestmentsService`` (see ``core.py``).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from backend.constants.tables import TransactionsTableFields
from backend.services.investments.timeline import ValuationTimeline
from backend.utils import data_cache

HISHTALMUT_TYPE = "hishtalmut"
"""Investment ``type`` marking a Keren Hishtalmut account.

Matches ``insurance_accounts.policy_type`` so scraped policies and
manually-created KH investments share one identity.
"""

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
        the transactions recorded after it — otherwise falls back to the
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
        return self._timeline(investment.iloc[0]).current_value(_today())

    def get_total_values_at_dates(self, target_dates: list[str]) -> dict[str, float]:
        """Return the snapshot-resolved total portfolio value at many dates in one pass.

        Fetches every investment's snapshots and transactions **once**
        instead of once per date. This turns the net-worth-over-time chart
        (which values the portfolio at each month end) from an O(months ×
        investments) database walk into O(investments) — the per-month
        resolution then happens in-memory.

        Per investment and per date the resolution is
        ``ValuationTimeline.value_at``. Closed investments are included: their
        derived zero values them at 0 after their last transaction and at
        their pre-close value before it.

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
        for _, inv in investments.iterrows():
            timeline = self._timeline(inv)
            for target_date in target_dates:
                totals[target_date] += timeline.value_at(target_date)
        return totals

    def _timeline(
        self, inv: pd.Series, transactions_df: pd.DataFrame | None = None
    ) -> ValuationTimeline:
        """Build an investment's valuation timeline.

        Parameters
        ----------
        inv : pd.Series
            The investment row.
        transactions_df : pd.DataFrame, optional
            Its transactions, when the caller already fetched them.

        Returns
        -------
        ValuationTimeline
            Its transactions, stored snapshots and closed state.
        """
        investment_id = int(inv["id"])
        closed_date = inv.get("closed_date")
        closed = str(closed_date) if pd.notna(closed_date) else None
        if transactions_df is None:
            inputs = self._cached_inputs(investment_id, inv["category"], inv["tag"])
            if (
                inputs is not None
                and inputs.timeline.is_closed == bool(inv["is_closed"])
                and inputs.closed_date == closed
            ):
                return inputs.timeline
            transactions_df = self._get_all_transactions_for_investment(
                inv["category"], inv["tag"], investment_id=investment_id
            )
        return ValuationTimeline(
            transactions_df,
            self.snapshots_repo.get_snapshots_for_investment(investment_id),
            is_closed=bool(inv["is_closed"]),
            closed_date=closed,
        )

    def _valuation_inputs(self) -> dict[int, "ValuationInputs"]:
        """Return every investment's transactions, snapshots and timeline.

        Built in one pass — one analysis frame, one snapshot query, one
        insurance query — and shared across requests through ``data_cache``
        until the next write. Six endpoints (the investments list, the
        portfolio, its balance history, net worth over time and both
        retirement-plan reads) value every holding, and each used to rebuild
        each holding's inputs about twice per request.

        Lock order: this key sits above the transaction reads (it calls
        ``get_data_for_analysis``); nothing under the transactions may value
        an investment.

        Returns
        -------
        dict[int, ValuationInputs]
            Investment id to its inputs. Shared: callers copy the frames
            (:meth:`_get_all_transactions_for_investment` does) and treat the
            timeline as read-only.
        """
        return data_cache.cached(
            self.db, ("investments.valuation_inputs",), self._build_valuation_inputs
        )

    def _build_valuation_inputs(self) -> dict[int, "ValuationInputs"]:
        """Build :meth:`_valuation_inputs`'s map with bulk reads."""
        investments = self.investments_repo.get_all_investments(include_closed=True)
        if investments.empty:
            return {}
        analysis = self.transactions_service.get_data_for_analysis()
        snapshots = self.snapshots_repo.get_all_by_investment()
        policies = [
            str(p) for p in investments["insurance_policy_id"] if p and pd.notna(p)
        ]
        insurance = self.transactions_repo.insurance_repo.get_for_policies(policies)
        no_snapshots = self.snapshots_repo.get_snapshots_for_investment(-1)

        inputs: dict[int, ValuationInputs] = {}
        for _, inv in investments.iterrows():
            investment_id = int(inv["id"])
            policy_id = inv.get("insurance_policy_id")
            linked = bool(policy_id) and pd.notna(policy_id)
            own_snapshots = snapshots.get(investment_id, no_snapshots)
            transactions = self._assemble_transactions(
                _by_tag(analysis, inv["category"], inv["tag"]),
                insurance.get(str(policy_id), pd.DataFrame()).copy()
                if linked
                else None,
                own_snapshots,
            )
            closed_date = inv.get("closed_date")
            closed = str(closed_date) if pd.notna(closed_date) else None
            inputs[investment_id] = ValuationInputs(
                category=inv["category"],
                tag=inv["tag"],
                transactions=transactions,
                closed_date=closed,
                timeline=ValuationTimeline(
                    transactions,
                    own_snapshots,
                    is_closed=bool(inv["is_closed"]),
                    closed_date=closed,
                ),
            )
        return inputs

    def _cached_inputs(
        self, investment_id: int, category: str, tag: str
    ) -> "ValuationInputs | None":
        """Return one investment's shared inputs when they answer this question.

        Parameters
        ----------
        investment_id : int
            The investment.
        category, tag : str
            The category and tag the caller values it by. A caller asking
            about a different pair than the stored one gets ``None`` and
            fetches its own.

        Returns
        -------
        ValuationInputs or None
            The shared inputs, or ``None`` when the session would not be
            served from the cache (an in-memory database or pending changes —
            building every holding to answer for one would only cost) or the
            pair differs.
        """
        if not data_cache.is_cacheable(self.db):
            return None
        inputs = self._valuation_inputs().get(int(investment_id))
        if inputs is None or inputs.category != category or inputs.tag != tag:
            return None
        return inputs

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
        snapshot). A closed investment's line ends at its derived zero.

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

        timeline = self._timeline(investment.iloc[0])
        if timeline.is_empty:
            return []

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        # A closed investment's line ends at its zero.
        if timeline.closing_date is not None:
            end_ts = min(end_ts, pd.Timestamp(timeline.closing_date))
        sample_dates = pd.DatetimeIndex([start_ts, end_ts]).union(
            pd.date_range(start=start_ts, end=end_ts, freq="MS")
        )
        events = pd.to_datetime(
            [*timeline.event_dates, *timeline.snapshot_dates]
        ).unique()
        sample_dates = sample_dates.union(
            events[(events >= start_ts) & (events <= end_ts)]
        )
        return timeline.series(sample_dates)

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
        timeline = self._timeline(inv, transactions_df)

        if transactions_df.empty:
            # No transactions — check if there's a snapshot (e.g. insurance-synced)
            if not inv["is_closed"]:
                today = _today()
                if timeline.snapshot_dates and timeline.snapshot_dates[0] <= today:
                    balance = timeline.current_value(today)
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

        current_balance = timeline.current_value(_today())
        if inv["is_closed"]:
            absolute_profit_loss = total_withdrawals - cost_basis
        else:
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
            Matching transactions from the merged analysis table. The caller
            owns it.
        """
        if investment_id is not None:
            inputs = self._cached_inputs(investment_id, category, tag)
            if inputs is not None:
                return inputs.transactions.copy()
        return self._fetch_transactions_for_investment(category, tag, investment_id)

    def _fetch_transactions_for_investment(
        self, category: str, tag: str, investment_id: int | None = None
    ) -> pd.DataFrame:
        """Read one investment's transactions without the shared map.

        :meth:`_get_all_transactions_for_investment` for write paths, which
        would otherwise rebuild every holding after each of their own commits.

        Parameters
        ----------
        category, tag : str
            The investment's category and tag.
        investment_id : int, optional
            Investment ID used to look up insurance linkage.

        Returns
        -------
        pd.DataFrame
            As :meth:`_get_all_transactions_for_investment`.
        """
        manual_txns = self.transactions_service.get_transactions_by_tag(category, tag)
        if investment_id is None:
            return manual_txns

        inv_df = self.investments_repo.get_by_id(investment_id)
        policy_id = inv_df.iloc[0].get("insurance_policy_id")
        if not policy_id or pd.isna(policy_id):
            return manual_txns

        return self._assemble_transactions(
            manual_txns,
            self.transactions_repo.insurance_repo.get_for_policy(policy_id),
            self.snapshots_repo.get_snapshots_for_investment(investment_id),
        )

    def _assemble_transactions(
        self,
        manual_txns: pd.DataFrame,
        ins_txns: pd.DataFrame | None,
        snapshots: pd.DataFrame,
    ) -> pd.DataFrame:
        """Combine an investment's manual and insurance rows, opening row included.

        Parameters
        ----------
        manual_txns : pd.DataFrame
            Its rows from the analysis frame.
        ins_txns : pd.DataFrame or None
            Its policy's insurance rows (owned — amounts are negated in
            place), or ``None`` when it is not insurance-linked: its manual
            rows are then the whole answer.
        snapshots : pd.DataFrame
            Its stored snapshots, for the opening-balance row.

        Returns
        -------
        pd.DataFrame
            The investment's transactions.
        """
        if ins_txns is None:
            return manual_txns

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

        return self._with_opening_balance(snapshots, combined)

    @staticmethod
    def _with_opening_balance(
        snapshots: pd.DataFrame, transactions_df: pd.DataFrame
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
        snapshots : pd.DataFrame
            The stored snapshots of an insurance-linked investment.
        transactions_df : pd.DataFrame
            Its manual and insurance transactions (may be empty).

        Returns
        -------
        pd.DataFrame
            ``transactions_df`` with an ``OPENING_BALANCE_COLUMN`` column, plus
            the opening row when the first snapshot exceeds the deposits.
        """
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


@dataclass(frozen=True)
class ValuationInputs:
    """One investment's valuation inputs, as ``ValuationMixin`` shares them.

    Attributes
    ----------
    category, tag : str
        The pair its transactions were selected by.
    transactions : pd.DataFrame
        Its transactions, opening-balance row included (shared — copy first).
    closed_date : str or None
        The closure date the timeline was built with.
    timeline : ValuationTimeline
        Its valuation timeline (read-only).
    """

    category: str
    tag: str
    transactions: pd.DataFrame
    closed_date: str | None
    timeline: ValuationTimeline


def _by_tag(analysis: pd.DataFrame, category: str, tag: str | None) -> pd.DataFrame:
    """Select one investment's rows from the analysis frame.

    The selection ``TransactionsService.get_transactions_by_tag`` makes, over
    a frame the caller already holds.
    """
    if analysis.empty:
        return analysis
    rows = analysis[analysis[TransactionsTableFields.CATEGORY.value] == category]
    if tag:
        rows = rows[rows[TransactionsTableFields.TAG.value] == tag]
    return rows.reset_index(drop=True)


def _today() -> str:
    """Return today's date in ``YYYY-MM-DD`` format."""
    return date.today().strftime("%Y-%m-%d")
