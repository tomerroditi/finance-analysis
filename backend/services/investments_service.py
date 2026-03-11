"""
Investments service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for investment tracking and analysis.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.investment_snapshots_repository import InvestmentSnapshotsRepository
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
        self.snapshots_repo = InvestmentSnapshotsRepository(db)
        from backend.services.transactions_service import TransactionsService

        self.transactions_service = TransactionsService(db)

    def get_all_investments(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        """
        Get all investments as a list of JSON-safe dicts.

        Each record is enriched with ``latest_snapshot_date`` indicating the
        most recent balance snapshot, or ``None`` if no snapshots exist.

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
        records = df.to_dict(orient="records")

        for record in records:
            latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                record["id"], date.today().strftime("%Y-%m-%d")
            )
            record["latest_snapshot_date"] = latest["date"] if latest else None

            txns = self._get_all_transactions_for_investment(
                record["category"], record["tag"]
            )
            if not txns.empty:
                record["first_transaction_date"] = pd.to_datetime(txns["date"]).min().strftime("%Y-%m-%d")
            else:
                record["first_transaction_date"] = None

        return records

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

    def sync_from_insurance(self, insurance_meta: dict) -> None:
        """Create or update an Investment from scraped insurance account metadata.

        Only processes hishtalmut policies. Creates the Investment if not found
        by ``insurance_policy_id``, otherwise updates metadata fields. Upserts
        a ``"scraped"`` balance snapshot if balance data is present, without
        overwriting existing ``"manual"`` snapshots.

        Parameters
        ----------
        insurance_meta : dict
            Insurance account metadata with keys: ``policy_id``, ``policy_type``,
            ``provider``, ``account_name``, ``balance``, ``balance_date``,
            ``commission_deposits_pct``, ``commission_savings_pct``,
            ``liquidity_date``.
        """
        if insurance_meta.get("policy_type") != "hishtalmut":
            return

        from backend.constants.categories import INVESTMENTS_CATEGORY

        policy_id = insurance_meta["policy_id"]
        provider = insurance_meta.get("provider", "unknown")
        tag = f"Keren Hishtalmut - {provider}"

        existing = self.investments_repo.get_by_insurance_policy_id(policy_id)

        if existing.empty:
            # Check if an investment already exists by category+tag but isn't linked yet
            by_tag = self.investments_repo.get_by_category_tag(INVESTMENTS_CATEGORY, tag)
            if not by_tag.empty:
                # Link the existing investment to this policy
                inv_id = int(by_tag.iloc[0]["id"])
                self.investments_repo.update_investment(
                    inv_id,
                    insurance_policy_id=policy_id,
                    name=insurance_meta["account_name"],
                    commission_deposit=insurance_meta.get("commission_deposits_pct"),
                    commission_management=insurance_meta.get("commission_savings_pct"),
                    liquidity_date=insurance_meta.get("liquidity_date"),
                )
            else:
                self.investments_repo.create_investment(
                    category=INVESTMENTS_CATEGORY,
                    tag=tag,
                    type_="hishtalmut",
                    name=insurance_meta["account_name"],
                    interest_rate_type="variable",
                    commission_deposit=insurance_meta.get("commission_deposits_pct"),
                    commission_management=insurance_meta.get("commission_savings_pct"),
                    liquidity_date=insurance_meta.get("liquidity_date"),
                )
                created = self.investments_repo.get_by_category_tag(INVESTMENTS_CATEGORY, tag)
                if not created.empty:
                    inv_id = int(created.iloc[0]["id"])
                    self.investments_repo.update_investment(
                        inv_id, insurance_policy_id=policy_id
                    )
        else:
            inv_id = int(existing.iloc[0]["id"])
            self.investments_repo.update_investment(
                inv_id,
                name=insurance_meta["account_name"],
                commission_deposit=insurance_meta.get("commission_deposits_pct"),
                commission_management=insurance_meta.get("commission_savings_pct"),
                liquidity_date=insurance_meta.get("liquidity_date"),
            )

        balance = insurance_meta.get("balance")
        balance_date = insurance_meta.get("balance_date")
        if balance is not None and balance_date is not None:
            inv_df = self.investments_repo.get_by_insurance_policy_id(policy_id)
            inv_id = int(inv_df.iloc[0]["id"])

            existing_snapshots = self.snapshots_repo.get_snapshots_for_investment(inv_id)
            if not existing_snapshots.empty:
                date_match = existing_snapshots[existing_snapshots["date"] == balance_date]
                if not date_match.empty and date_match.iloc[0]["source"] == "manual":
                    return

            self.snapshots_repo.upsert_snapshot(inv_id, balance_date, balance, source="scraped")

    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """
        Mark an investment as closed.

        Automatically creates a balance snapshot of 0 on the last transaction
        date for this investment, since a closed investment has no remaining
        value. If no transactions exist, uses the closure date.

        Parameters
        ----------
        investment_id : int
            ID of the investment to close.
        closed_date : str
            Closure date in ``YYYY-MM-DD`` format.
        """
        self.investments_repo.close_investment(investment_id, closed_date)

        inv = self.investments_repo.get_by_id(investment_id).iloc[0]
        txns = self._get_all_transactions_for_investment(inv["category"], inv["tag"])
        if not txns.empty:
            txns["date_parsed"] = pd.to_datetime(txns["date"])
            last_txn_date = txns["date_parsed"].max().strftime("%Y-%m-%d")
        else:
            last_txn_date = closed_date
        self.create_balance_snapshot(investment_id, last_txn_date, 0.0)

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

    # ── Balance Snapshot Methods ──────────────────────────────────────

    def create_balance_snapshot(
        self,
        investment_id: int,
        date: str,
        balance: float,
        source: str = "manual",
    ) -> None:
        """Create or update a balance snapshot for an investment.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        date : str
            Snapshot date in ``YYYY-MM-DD`` format.
        balance : float
            Market value on this date.
        source : str
            Origin: ``"manual"``, ``"scraped"``, or ``"calculated"``.
        """
        self.snapshots_repo.upsert_snapshot(investment_id, date, balance, source)

    def get_balance_snapshots(self, investment_id: int) -> List[Dict[str, Any]]:
        """Get all balance snapshots for an investment.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        list[dict]
            Snapshot records ordered by date, with ``NaN`` replaced by ``None``.
        """
        df = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        if df.empty:
            return []
        df = df.replace({np.nan: None})
        return df.to_dict(orient="records")

    def update_balance_snapshot(self, snapshot_id: int, **fields) -> None:
        """Update a balance snapshot.

        Parameters
        ----------
        snapshot_id : int
            ID of the snapshot to update.
        **fields
            Column names and new values.
        """
        self.snapshots_repo.update_snapshot(snapshot_id, **fields)

    def delete_balance_snapshot(self, snapshot_id: int) -> None:
        """Delete a balance snapshot by ID.

        Parameters
        ----------
        snapshot_id : int
            ID of the snapshot to delete.
        """
        self.snapshots_repo.delete_snapshot(snapshot_id)

    def calculate_fixed_rate_snapshots(
        self,
        investment_id: int,
        end_date: Optional[str] = None,
    ) -> None:
        """Generate calculated balance snapshots for a fixed-rate investment.

        Replays the transaction timeline with daily compounding to produce
        monthly snapshots. Existing ``"calculated"`` snapshots are cleared first;
        manual/scraped snapshots are preserved.

        Parameters
        ----------
        investment_id : int
            ID of the investment (must have ``interest_rate_type == "fixed"``
            and a non-null ``interest_rate``).
        end_date : str, optional
            End date for calculation in ``YYYY-MM-DD`` format.
            Defaults to today.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]

        if not inv.get("interest_rate") or inv.get("interest_rate_type") != "fixed":
            return

        annual_rate = float(inv["interest_rate"]) / 100.0
        daily_rate = (1 + annual_rate) ** (1 / 365) - 1

        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )
        if transactions_df.empty:
            return

        transactions_df = transactions_df.copy()
        transactions_df["date"] = pd.to_datetime(transactions_df["date"])
        transactions_df["amount"] = pd.to_numeric(
            transactions_df["amount"], errors="coerce"
        ).fillna(0.0)
        transactions_df = transactions_df.sort_values("date")

        start = transactions_df["date"].min().date()
        end = (
            datetime.strptime(end_date, "%Y-%m-%d").date()
            if end_date
            else date.today()
        )

        # Build a dict of date -> total transaction amount for that day
        txn_by_date = {}
        for _, row in transactions_df.iterrows():
            d = row["date"].date()
            txn_by_date[d] = txn_by_date.get(d, 0.0) + row["amount"]

        # Clear previous calculated snapshots
        self.snapshots_repo.delete_snapshots_for_investment(
            investment_id, source="calculated"
        )

        # Collect dates with manual/scraped snapshots to avoid overwriting
        existing_df = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        protected_dates: set = set()
        if not existing_df.empty:
            protected_dates = set(existing_df["date"].tolist())

        # Simulate daily compounding
        balance = 0.0
        current = start

        while current <= end:
            # Apply transactions for this day (negative = deposit adds to balance)
            if current in txn_by_date:
                balance -= txn_by_date[current]  # negate: deposit(-1000) -> +1000

            # Apply daily interest
            if balance > 0:
                balance *= 1 + daily_rate

            # Store monthly snapshots (first of month or end date)
            date_str = current.strftime("%Y-%m-%d")
            if (current.day == 1 or current == end) and date_str not in protected_dates:
                self.snapshots_repo.upsert_snapshot(
                    investment_id,
                    date_str,
                    round(balance, 2),
                    "calculated",
                )

            current += timedelta(days=1)

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
        all_inv_txns = self.transactions_repo.get_table(Services.MANUAL_INVESTMENTS.value)
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

    def get_total_prior_wealth(self, include_closed: bool = True) -> float:
        """
        Sum prior_wealth_amount across investments.

        Parameters
        ----------
        include_closed : bool, optional
            When ``True`` (default), includes closed investments.
            Use ``False`` for overview identity calculations where closed
            investment capital is already reflected in bank balances.

        Returns
        -------
        float
            Total prior wealth across selected investments.
        """
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

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

            - ``series`` – list of per-investment dicts with ``name`` and
              ``data`` (list of ``{"date": str, "balance": float}``).
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
                    "name": inv["name"],
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
            inv["category"], inv["tag"]
        )
        return self._calculate_balance_from_transactions(transactions_df)

    def calculate_balance_over_time(
        self, investment_id: int, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Calculate balance at daily intervals between two dates for charting.

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
            List of ``{"date": str, "balance": float}`` dicts, one per day.
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

        # For closed investments, stop at the last transaction date
        actual_end_date = end_date
        if inv["is_closed"] and not transactions_df.empty:
            last_txn_date = pd.to_datetime(transactions_df["date"]).max().date()
            requested_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            actual_end_date = min(last_txn_date, requested_end_date).strftime("%Y-%m-%d")

        snapshots_df = self.snapshots_repo.get_snapshots_for_investment(investment_id)

        if snapshots_df.empty:
            # No snapshots — use transaction-based approach
            dates = pd.date_range(start=start_date, end=actual_end_date, freq="D")
            balances = []
            for d in dates:
                balance = self._calculate_balance_from_transactions(
                    transactions_df, as_of_date=d.strftime("%Y-%m-%d")
                )
                balances.append({"date": d.strftime("%Y-%m-%d"), "balance": balance})
        else:
            # Snapshot-aware: interpolate between snapshots
            snapshots_df = snapshots_df.copy()
            snapshots_df["date"] = pd.to_datetime(snapshots_df["date"])
            snapshots_df = snapshots_df.sort_values("date")

            dates = pd.date_range(start=start_date, end=actual_end_date, freq="D")
            balances = []

            for d in dates:
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
