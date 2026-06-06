"""Budget month override repository with SQLAlchemy ORM."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.budget_month_override import BudgetMonthOverride


class BudgetMonthOverrideRepository:
    """
    Repository for managing budget month override records using ORM.

    Handles CRUD operations for transaction/split budget-month reassignments.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """
        Get all budget month overrides.

        Returns
        -------
        pd.DataFrame
            DataFrame of override records (empty if none exist).
        """
        return pd.read_sql(select(BudgetMonthOverride), self.db.bind)

    def get_by_id(self, override_id: int) -> BudgetMonthOverride | None:
        """
        Get a budget month override by its primary key.

        Parameters
        ----------
        override_id : int
            ID of the override record.

        Returns
        -------
        BudgetMonthOverride or None
            The override record, or None if not found.
        """
        return self.db.get(BudgetMonthOverride, override_id)

    def get_for_source(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
    ) -> BudgetMonthOverride | None:
        """
        Get the existing override for a specific source, if any.

        Parameters
        ----------
        source_type : str
            Type of source: 'transaction' or 'split'.
        source_id : int
            ID of the source.
        source_table : str
            Table where the source lives.

        Returns
        -------
        BudgetMonthOverride or None
            The override if one exists, None otherwise.
        """
        stmt = (
            select(BudgetMonthOverride)
            .where(BudgetMonthOverride.source_type == source_type)
            .where(BudgetMonthOverride.source_id == source_id)
            .where(BudgetMonthOverride.source_table == source_table)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
        override_year: int,
        override_month: int,
    ) -> BudgetMonthOverride:
        """
        Create or update the override for a source.

        Parameters
        ----------
        source_type : str
            Type of source: 'transaction' or 'split'.
        source_id : int
            ID of the source.
        source_table : str
            Table where the source lives.
        override_year : int
            Target calendar year for the budget.
        override_month : int
            Target calendar month (1-12) for the budget.

        Returns
        -------
        BudgetMonthOverride
            The created or updated override record.
        """
        existing = self.get_for_source(source_type, source_id, source_table)
        if existing:
            existing.override_year = override_year
            existing.override_month = override_month
            self.db.commit()
            self.db.refresh(existing)
            return existing

        override = BudgetMonthOverride(
            source_type=source_type,
            source_id=source_id,
            source_table=source_table,
            override_year=override_year,
            override_month=override_month,
        )
        self.db.add(override)
        self.db.commit()
        self.db.refresh(override)
        return override

    def delete(self, override_id: int) -> None:
        """
        Delete a budget month override.

        Parameters
        ----------
        override_id : int
            ID of the override to delete.
        """
        override = self.db.get(BudgetMonthOverride, override_id)
        if override:
            self.db.delete(override)
            self.db.commit()

    def delete_for_source(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
    ) -> None:
        """
        Delete the override for a specific source, if it exists.

        Parameters
        ----------
        source_type : str
            Type of source: 'transaction' or 'split'.
        source_id : int
            ID of the source.
        source_table : str
            Table where the source lives.
        """
        existing = self.get_for_source(source_type, source_id, source_table)
        if existing:
            self.db.delete(existing)
            self.db.commit()
