"""
Liabilities repository with SQLAlchemy ORM.
"""

from datetime import datetime

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.constants.categories import LIABILITIES_CATEGORY
from backend.errors import EntityNotFoundException
from backend.models.liability import Liability, LiabilityTransaction


class LiabilitiesRepository:
    """
    Repository for managing liability tracking records using ORM.
    """

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def create_liability(
        self,
        name: str,
        tag: str,
        principal_amount: float,
        interest_rate: float,
        term_months: int,
        start_date: str,
        lender: str = None,
        notes: str = None,
    ) -> None:
        """Create a new liability record.

        Parameters
        ----------
        name : str
            Human-readable name for the liability.
        tag : str
            Tag identifying this specific liability.
        principal_amount : float
            Original loan amount.
        interest_rate : float
            Annual interest rate as percentage (e.g. 4.5 for 4.5%).
        term_months : int
            Loan duration in months.
        start_date : str
            Date the loan was taken, in YYYY-MM-DD format.
        lender : str, optional
            Name of the lending institution.
        notes : str, optional
            Free-text notes about the liability.

        Returns
        -------
        None
        """
        new_liability = Liability(
            name=name,
            tag=tag,
            category=LIABILITIES_CATEGORY,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            start_date=start_date,
            lender=lender,
            notes=notes,
            created_date=datetime.today().strftime("%Y-%m-%d"),
        )
        self.db.add(new_liability)
        self.db.commit()

    def get_all_liabilities(self, include_paid_off: bool = False) -> pd.DataFrame:
        """Get all liabilities, optionally including paid-off ones.

        Parameters
        ----------
        include_paid_off : bool
            When True, paid-off liabilities are included in the result.
            Defaults to False.

        Returns
        -------
        pd.DataFrame
            All matching liability records with full liability columns.
        """
        stmt = select(Liability)
        if not include_paid_off:
            stmt = stmt.where(Liability.is_paid_off == 0)

        records = self.db.execute(stmt).scalars().all()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame([r.__dict__ for r in records])
        return df.drop(columns=["_sa_instance_state"], errors="ignore")

    def get_by_id(self, liability_id: int) -> pd.DataFrame:
        """Get a liability by its ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to retrieve.

        Returns
        -------
        pd.DataFrame
            Single-row DataFrame containing the liability record.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        stmt = select(Liability).where(Liability.id == liability_id)
        records = self.db.execute(stmt).scalars().all()
        if not records:
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )
        df = pd.DataFrame([r.__dict__ for r in records])
        return df.drop(columns=["_sa_instance_state"], errors="ignore")

    def update_liability(self, liability_id: int, **fields) -> None:
        """Update a liability by ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to update.
        **fields
            Keyword arguments mapping column names to their new values.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        if not fields:
            return

        stmt = update(Liability).where(Liability.id == liability_id).values(**fields)
        result = self.db.execute(stmt)

        if result.rowcount == 0:
            self.db.rollback()
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )

        self.db.commit()

    def mark_paid_off(self, liability_id: int, paid_off_date: str) -> None:
        """Mark a liability as paid off.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to mark as paid off.
        paid_off_date : str
            Date the liability was paid off, in YYYY-MM-DD format.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        stmt = (
            update(Liability)
            .where(Liability.id == liability_id)
            .values(is_paid_off=1, paid_off_date=paid_off_date)
        )
        result = self.db.execute(stmt)

        if result.rowcount == 0:
            self.db.rollback()
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )

        self.db.commit()

    def reopen(self, liability_id: int) -> None:
        """Reopen a paid-off liability.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to reopen.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        stmt = (
            update(Liability)
            .where(Liability.id == liability_id)
            .values(is_paid_off=0, paid_off_date=None)
        )
        result = self.db.execute(stmt)

        if result.rowcount == 0:
            self.db.rollback()
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )

        self.db.commit()

    def get_liability_transactions(self, liability_id: int) -> list[LiabilityTransaction]:
        """Get all auto-generated transactions for a liability.

        Parameters
        ----------
        liability_id : int
            FK of the owning liability.

        Returns
        -------
        list[LiabilityTransaction]
            All generated transactions for this liability, ordered by date.
        """
        stmt = (
            select(LiabilityTransaction)
            .where(LiabilityTransaction.liability_id == liability_id)
            .order_by(LiabilityTransaction.date)
        )
        return list(self.db.execute(stmt).scalars().all())

    def add_liability_transaction(self, **fields) -> None:
        """Create an auto-generated liability transaction.

        Parameters
        ----------
        **fields
            Fields for the LiabilityTransaction model.
        """
        self.db.add(LiabilityTransaction(**fields))

    def commit(self) -> None:
        """Commit the current transaction."""
        self.db.commit()

    def delete_liability(self, liability_id: int) -> None:
        """Delete a liability by ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to delete.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        # Delete child transactions first (SQLite may not enforce FK CASCADE)
        self.db.execute(
            delete(LiabilityTransaction).where(
                LiabilityTransaction.liability_id == liability_id
            )
        )
        stmt = delete(Liability).where(Liability.id == liability_id)
        result = self.db.execute(stmt)

        if result.rowcount == 0:
            self.db.rollback()
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )

        self.db.commit()
