"""
Balance-snapshot operations for the investments service.

Provides the ``SnapshotsMixin`` with snapshot CRUD and the fixed-rate
snapshot generator (daily compounding). Mixed into ``InvestmentsService``
(see ``core.py``).
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class SnapshotsMixin:
    """Balance-snapshot methods for ``InvestmentsService``."""

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
        """Generate calculated balance snapshots for a rate-bearing investment.

        Replays the transaction timeline with daily compounding to produce
        monthly snapshots. Existing ``"calculated"`` snapshots are cleared first;
        manual/scraped snapshots are preserved.

        Supports two rate types:

        - ``fixed`` — constant ``interest_rate`` for the whole timeline.
        - ``prime_linked`` — the rate is the Israeli prime rate plus
          ``rate_spread`` and follows every Bank of Israel decision; the
          daily rate is re-derived whenever the walk crosses a rate step.
          Falls back to the flat ``interest_rate`` when the rate series
          is empty.

        Parameters
        ----------
        investment_id : int
            ID of the investment (``interest_rate_type == "fixed"`` with a
            non-null ``interest_rate``, or ``"prime_linked"`` with a
            non-null ``rate_spread``).
        end_date : str, optional
            End date for calculation in ``YYYY-MM-DD`` format.
            Defaults to today.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]

        rate_type = inv.get("interest_rate_type")
        spread = inv.get("rate_spread")
        spread = None if pd.isna(spread) else float(spread)
        is_fixed = rate_type == "fixed" and bool(inv.get("interest_rate"))
        is_prime = rate_type == "prime_linked" and spread is not None
        if not is_fixed and not is_prime:
            return

        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=investment_id
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

        # Piecewise-constant daily-rate curve: [(effective_date, daily_rate)],
        # ascending. Fixed investments get a single step; prime-linked ones
        # get one step per Bank of Israel decision (prime + spread).
        def _daily(annual_pct: float) -> float:
            return (1 + annual_pct / 100.0) ** (1 / 365) - 1

        rate_curve: List[tuple] = []
        if is_prime:
            from backend.services.rates_service import RatesService

            prime_steps = RatesService(self.db).get_prime_steps(
                start.strftime("%Y-%m-%d")
            )
            rate_curve = [
                (
                    datetime.strptime(s["date"], "%Y-%m-%d").date(),
                    _daily(s["value"] + spread),
                )
                for s in prime_steps
            ]
        if not rate_curve:
            # Fixed rate, or prime-linked with an empty rate series.
            flat_rate = inv.get("interest_rate")
            if not flat_rate:
                return
            rate_curve = [(start, _daily(float(flat_rate)))]

        # Build a dict of date -> total transaction amount for that day.
        # ``date`` is a datetime dtype here (parsed via ``pd.to_datetime`` above),
        # so ``.dt.date`` yields the same per-row ``date`` objects the prior
        # ``row["date"].date()`` loop produced. Vectorized groupby replaces the
        # row-wise iterrows accumulation.
        txn_by_date = (
            transactions_df.groupby(transactions_df["date"].dt.date)["amount"]
            .sum()
            .to_dict()
        )

        # Clear previous calculated snapshots
        self.snapshots_repo.delete_snapshots_for_investment(
            investment_id, source="calculated"
        )

        # Collect dates with manual/scraped snapshots to avoid overwriting
        existing_df = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        protected_dates: set = set()
        if not existing_df.empty:
            protected_dates = set(existing_df["date"].tolist())

        # Simulate daily compounding, advancing along the rate curve
        balance = 0.0
        current = start
        daily_rate = rate_curve[0][1]
        next_step = 1

        while current <= end:
            # Pick up rate steps that have come into effect
            while next_step < len(rate_curve) and rate_curve[next_step][0] <= current:
                daily_rate = rate_curve[next_step][1]
                next_step += 1

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

    def recalculate_prime_linked_snapshots(self) -> int:
        """Regenerate calculated snapshots for every open prime-linked investment.

        Called after a Bank of Israel rate refresh appends a new decision,
        so prime-linked balances pick up the change without waiting for the
        next manual recalculation.

        Returns
        -------
        int
            Number of investments recalculated.
        """
        df = self.investments_repo.get_all_investments(include_closed=False)
        if df.empty or "interest_rate_type" not in df.columns:
            return 0

        prime_linked = df[df["interest_rate_type"] == "prime_linked"]
        for _, row in prime_linked.iterrows():
            self.calculate_fixed_rate_snapshots(int(row["id"]))
        return len(prime_linked)
