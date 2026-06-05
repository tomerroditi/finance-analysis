"""Budget month override service with business logic."""

from typing import Literal, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.transaction import SplitTransaction
from backend.repositories.budget_month_override_repository import (
    BudgetMonthOverrideRepository,
)
from backend.repositories.transactions_repository import TransactionsRepository


class BudgetMonthOverrideService:
    """
    Service for reassigning a transaction to a different month in the budget.

    A transaction always keeps its real ``date``; an override only changes
    which month the monthly budget view counts it in. Movement is capped at
    one month before or after the transaction's real month.
    """

    def __init__(self, db: Session):
        """
        Initialize the budget month override service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = BudgetMonthOverrideRepository(db)
        self.transactions_repo = TransactionsRepository(db)

    def _get_source_date(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
    ) -> Optional[pd.Timestamp]:
        """
        Resolve the real transaction date for a source.

        Parameters
        ----------
        source_type : str
            Either 'transaction' or 'split'.
        source_id : int
            unique_id for transactions, split id for splits.
        source_table : str
            Table where the source lives.

        Returns
        -------
        pd.Timestamp or None
            The transaction's real date, or None if it could not be resolved.
        """
        if source_type == "split":
            split = self.db.get(SplitTransaction, source_id)
            if not split:
                return None
            repo = self.transactions_repo.repo_map.get(split.source)
            if not repo:
                return None
            parent = self.db.execute(
                select(repo.model).where(repo.model.unique_id == split.transaction_id)
            ).scalar_one_or_none()
            return pd.to_datetime(parent.date) if parent else None

        repo = self.transactions_repo.repo_map.get(source_table)
        if not repo:
            return None
        txn = self.db.execute(
            select(repo.model).where(repo.model.unique_id == source_id)
        ).scalar_one_or_none()
        return pd.to_datetime(txn.date) if txn else None

    @staticmethod
    def _month_delta(
        from_year: int, from_month: int, to_year: int, to_month: int
    ) -> int:
        """Return the signed number of months from one (year, month) to another."""
        return (to_year - from_year) * 12 + (to_month - from_month)

    def set_override(
        self,
        source_type: Literal["transaction", "split"],
        source_id: int,
        source_table: str,
        override_year: int,
        override_month: int,
    ) -> dict:
        """
        Reassign a transaction to a different budget month (capped at +/- 1 month).

        If the target month equals the transaction's real month, any existing
        override is removed instead (the transaction reverts to its natural month).

        Parameters
        ----------
        source_type : str
            Either 'transaction' or 'split'.
        source_id : int
            unique_id for transactions, split id for splits.
        source_table : str
            Table where the source lives.
        override_year : int
            Target calendar year.
        override_month : int
            Target calendar month (1-12).

        Returns
        -------
        dict
            The resulting override record, or ``{"removed": True}`` when the
            target is the transaction's real month.

        Raises
        ------
        ValidationException
            If the month is out of range or the move exceeds one month.
        EntityNotFoundException
            If the source transaction cannot be found.
        """
        if not 1 <= override_month <= 12:
            raise ValidationException("override_month must be between 1 and 12")

        source_date = self._get_source_date(source_type, source_id, source_table)
        if source_date is None:
            raise EntityNotFoundException(
                f"Could not resolve {source_type} {source_id} in {source_table}"
            )

        delta = self._month_delta(
            source_date.year, source_date.month, override_year, override_month
        )
        if abs(delta) > 1:
            raise ValidationException(
                "A transaction can only be moved one month before or after "
                "its original month"
            )

        # Target is the real month — clear any override so it reverts naturally.
        if delta == 0:
            self.repo.delete_for_source(source_type, source_id, source_table)
            return {"removed": True}

        override = self.repo.upsert(
            source_type=source_type,
            source_id=source_id,
            source_table=source_table,
            override_year=override_year,
            override_month=override_month,
        )
        return self._to_dict(override)

    def remove_override(self, override_id: int) -> None:
        """
        Remove a budget month override by id.

        Parameters
        ----------
        override_id : int
            ID of the override to remove.

        Raises
        ------
        EntityNotFoundException
            If the override does not exist.
        """
        override = self.repo.get_by_id(override_id)
        if not override:
            raise EntityNotFoundException(
                f"Budget month override {override_id} not found"
            )
        self.repo.delete(override_id)

    def get_all(self) -> list[dict]:
        """
        Get all budget month overrides.

        Returns
        -------
        list[dict]
            List of override records.
        """
        df = self.repo.get_all()
        return df.to_dict(orient="records") if not df.empty else []

    def get_override_map(self) -> dict[str, dict]:
        """
        Build lookup maps of active overrides for budget filtering.

        Returns
        -------
        dict[str, dict]
            Dictionary with keys 'transaction' and 'split', each mapping a
            source_id to a ``(override_year, override_month)`` tuple.
        """
        df = self.repo.get_all()
        if df.empty:
            return {"transaction": {}, "split": {}}

        result: dict[str, dict] = {"transaction": {}, "split": {}}
        for row in df.itertuples(index=False):
            bucket = result.get(row.source_type)
            if bucket is None:
                continue
            bucket[row.source_id] = (int(row.override_year), int(row.override_month))
        return result

    @staticmethod
    def _to_dict(override) -> dict:
        """Serialize a BudgetMonthOverride ORM object to a plain dict."""
        return {
            "id": override.id,
            "source_type": override.source_type,
            "source_id": override.source_id,
            "source_table": override.source_table,
            "override_year": override.override_year,
            "override_month": override.override_month,
        }
