"""
Investment balance snapshots repository with SQLAlchemy ORM.
"""

from typing import Optional

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot


class InvestmentSnapshotsRepository:
    """Repository for managing investment balance snapshots using ORM.

    Provides CRUD operations for point-in-time balance recordings
    of tracked investments. Enforces one snapshot per investment per
    date via upsert semantics.
    """

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def upsert_snapshot(
        self,
        investment_id: int,
        date: str,
        balance: float,
        source: str = "manual",
    ) -> None:
        """Create or update a balance snapshot for an investment on a given date.

        If a snapshot already exists for the ``(investment_id, date)`` pair,
        its ``balance`` and ``source`` fields are updated. Otherwise a new
        record is inserted.

        Parameters
        ----------
        investment_id : int
            Foreign key referencing the investment record.
        date : str
            Snapshot date in ``YYYY-MM-DD`` format.
        balance : float
            Market value of the investment on this date.
        source : str
            How the snapshot was created (``"manual"``, ``"scraped"``,
            or ``"calculated"``). Defaults to ``"manual"``.
        """
        existing = (
            self.db.query(InvestmentBalanceSnapshot)
            .filter_by(investment_id=investment_id, date=date)
            .first()
        )

        if existing:
            existing.balance = balance
            existing.source = source
        else:
            snapshot = InvestmentBalanceSnapshot(
                investment_id=investment_id,
                date=date,
                balance=balance,
                source=source,
            )
            self.db.add(snapshot)

        self.db.commit()

    def get_snapshots_for_investment(self, investment_id: int) -> pd.DataFrame:
        """Get all snapshots for an investment ordered by date ascending.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to query.

        Returns
        -------
        pd.DataFrame
            All snapshot records for the investment, sorted by date.
        """
        stmt = (
            select(InvestmentBalanceSnapshot)
            .where(InvestmentBalanceSnapshot.investment_id == investment_id)
            .order_by(InvestmentBalanceSnapshot.date.asc())
        )
        return pd.read_sql(stmt, self.db.bind)

    def get_latest_snapshot_on_or_before(
        self, investment_id: int, target_date: str
    ) -> Optional[dict]:
        """Find the most recent snapshot on or before a target date.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to query.
        target_date : str
            Upper bound date in ``YYYY-MM-DD`` format (inclusive).

        Returns
        -------
        dict or None
            A dictionary with snapshot fields if found, otherwise ``None``.
        """
        snapshot = (
            self.db.query(InvestmentBalanceSnapshot)
            .filter(
                InvestmentBalanceSnapshot.investment_id == investment_id,
                InvestmentBalanceSnapshot.date <= target_date,
            )
            .order_by(InvestmentBalanceSnapshot.date.desc())
            .first()
        )

        if snapshot is None:
            return None

        return {
            "id": snapshot.id,
            "investment_id": snapshot.investment_id,
            "date": snapshot.date,
            "balance": snapshot.balance,
            "source": snapshot.source,
        }

    def update_snapshot(self, snapshot_id: int, **fields) -> None:
        """Update a snapshot by its ID.

        Parameters
        ----------
        snapshot_id : int
            Primary key of the snapshot to update.
        **fields
            Keyword arguments mapping column names to their new values.

        Raises
        ------
        EntityNotFoundException
            If no snapshot with the given ID exists.
        """
        if not fields:
            return

        stmt = (
            update(InvestmentBalanceSnapshot)
            .where(InvestmentBalanceSnapshot.id == snapshot_id)
            .values(**fields)
        )
        result = self.db.execute(stmt)
        self.db.commit()

        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No snapshot found with ID {snapshot_id}"
            )

    def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a snapshot by its ID.

        Parameters
        ----------
        snapshot_id : int
            Primary key of the snapshot to delete.

        Raises
        ------
        EntityNotFoundException
            If no snapshot with the given ID exists.
        """
        stmt = delete(InvestmentBalanceSnapshot).where(
            InvestmentBalanceSnapshot.id == snapshot_id
        )
        result = self.db.execute(stmt)
        self.db.commit()

        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No snapshot found with ID {snapshot_id}"
            )

    def delete_snapshots_for_investment(
        self, investment_id: int, source: Optional[str] = None
    ) -> None:
        """Delete all snapshots for an investment, optionally filtered by source.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment whose snapshots should be removed.
        source : str, optional
            When provided, only snapshots with this source value are deleted.
            When ``None``, all snapshots for the investment are removed.
        """
        stmt = delete(InvestmentBalanceSnapshot).where(
            InvestmentBalanceSnapshot.investment_id == investment_id
        )

        if source is not None:
            stmt = stmt.where(InvestmentBalanceSnapshot.source == source)

        self.db.execute(stmt)
        self.db.commit()
