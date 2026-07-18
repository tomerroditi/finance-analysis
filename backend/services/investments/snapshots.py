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
