"""
Investments repository with SQLAlchemy ORM.
"""

from datetime import datetime

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from backend.errors import EntityNotFoundException

from backend.models.investment import Investment
from backend.constants.tables import InvestmentsTableFields, Tables


class InvestmentsRepository:
    """
    Repository for managing investment tracking records using ORM.
    """

    table = Tables.INVESTMENTS.value

    id_col = InvestmentsTableFields.ID.value
    category_col = InvestmentsTableFields.CATEGORY.value
    tag_col = InvestmentsTableFields.TAG.value
    type_col = InvestmentsTableFields.TYPE.value
    name_col = InvestmentsTableFields.NAME.value
    is_closed_col = InvestmentsTableFields.IS_CLOSED.value
    created_date_col = InvestmentsTableFields.CREATED_DATE.value
    closed_date_col = InvestmentsTableFields.CLOSED_DATE.value
    notes_col = InvestmentsTableFields.NOTES.value

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def _assure_table_exists(self) -> None:
        pass

    def create_investment(
        self,
        category: str,
        tag: str,
        type_: str,
        name: str,
        interest_rate: float = None,
        interest_rate_type: str = "fixed",
        commission_deposit: float = None,
        commission_management: float = None,
        commission_withdrawal: float = None,
        liquidity_date: str = None,
        maturity_date: str = None,
        notes: str = None,
        insurance_policy_id: str = None,
    ) -> int:
        """Create a new investment record.

        Parameters
        ----------
        category : str
            Tag category the investment belongs to (e.g. "Stocks").
        tag : str
            Tag name identifying this investment within its category.
        type_ : str
            Investment type (e.g. "savings_account", "etf").
        name : str
            Human-readable display name for the investment.
        interest_rate : float, optional
            Annual interest rate expressed as a decimal.
        interest_rate_type : str
            Whether the rate is "fixed" or "variable". Defaults to "fixed".
        commission_deposit : float, optional
            Commission rate applied on deposits.
        commission_management : float, optional
            Ongoing management fee rate.
        commission_withdrawal : float, optional
            Commission rate applied on withdrawals.
        liquidity_date : str, optional
            Date when funds become accessible, in YYYY-MM-DD format.
        maturity_date : str, optional
            Maturity date of the investment, in YYYY-MM-DD format.
        notes : str, optional
            Free-text notes about the investment.
        insurance_policy_id : str, optional
            Linked insurance policy ID for auto-synced investments.

        Returns
        -------
        int
            Primary key of the newly created investment.
        """
        new_inv = Investment(
            category=category,
            tag=tag,
            type=type_,
            name=name,
            interest_rate=interest_rate,
            interest_rate_type=interest_rate_type,
            commission_deposit=commission_deposit,
            commission_management=commission_management,
            commission_withdrawal=commission_withdrawal,
            liquidity_date=liquidity_date,
            maturity_date=maturity_date,
            created_date=datetime.today().strftime("%Y-%m-%d"),
            notes=notes,
            insurance_policy_id=insurance_policy_id,
        )
        self.db.add(new_inv)
        self.db.commit()
        return new_inv.id

    def get_all_investments(self, include_closed: bool = False) -> pd.DataFrame:
        """Get all investments, optionally including closed ones.

        Parameters
        ----------
        include_closed : bool
            When True, closed investments are included in the result.
            Defaults to False.

        Returns
        -------
        pd.DataFrame
            All matching investment records with full investment columns.
        """
        stmt = select(Investment)
        if not include_closed:
            stmt = stmt.where(Investment.is_closed == 0)

        return pd.read_sql(stmt, self.db.bind)

    def get_by_id(self, investment_id: int) -> pd.DataFrame:
        """Get an investment by its ID.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to retrieve.

        Returns
        -------
        pd.DataFrame
            Single-row DataFrame containing the investment record.

        Raises
        ------
        EntityNotFoundException
            If no investment with the given ID exists.
        """
        stmt = select(Investment).where(Investment.id == investment_id)
        df = pd.read_sql(stmt, self.db.bind)
        if df.empty:
            raise EntityNotFoundException(
                f"No investment found with ID {investment_id}"
            )
        return df

    def get_by_category_tag(self, category: str, tag: str) -> pd.DataFrame:
        """Get an investment by category and tag.

        Parameters
        ----------
        category : str
            Category name to filter by.
        tag : str
            Tag name to filter by.

        Returns
        -------
        pd.DataFrame
            Matching investment rows, or empty DataFrame if not found.
        """
        stmt = select(Investment).where(
            Investment.category == category, Investment.tag == tag
        )
        return pd.read_sql(stmt, self.db.bind)

    def get_by_insurance_policy_id(self, policy_id: str) -> pd.DataFrame:
        """Find an investment linked to an insurance policy.

        Parameters
        ----------
        policy_id : str
            The insurance policy ID to look up.

        Returns
        -------
        pd.DataFrame
            Matching investment row, or empty DataFrame if not found.
        """
        stmt = select(Investment).where(
            Investment.insurance_policy_id == policy_id
        )
        return pd.read_sql(stmt, self.db.bind)

    def update_investment(self, investment_id: int, **fields) -> None:
        """Update an investment by ID.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to update.
        **fields
            Keyword arguments mapping column names to their new values.

        Raises
        ------
        EntityNotFoundException
            If no investment with the given ID exists.
        """
        if not fields:
            return

        stmt = update(Investment).where(Investment.id == investment_id).values(**fields)
        result = self.db.execute(stmt)
        self.db.commit()

        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No investment found with ID {investment_id}"
            )

    def update_prior_wealth(self, investment_id: int, amount: float) -> None:
        """Update the stored prior_wealth_amount for an investment.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to update.
        amount : float
            New prior_wealth_amount value to store.

        Raises
        ------
        EntityNotFoundException
            If no investment with the given ID exists.
        """
        stmt = (
            update(Investment)
            .where(Investment.id == investment_id)
            .values(prior_wealth_amount=amount)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No investment found with ID {investment_id}"
            )

    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """Close an investment by setting is_closed flag and closed_date.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to close.
        closed_date : str
            Date the investment was closed, in YYYY-MM-DD format.
        """
        stmt = (
            update(Investment)
            .where(Investment.id == investment_id)
            .values(is_closed=1, closed_date=closed_date)
        )
        self.db.execute(stmt)
        self.db.commit()

    def reopen_investment(self, investment_id: int) -> None:
        """Reopen a closed investment.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to reopen.
        """
        stmt = (
            update(Investment)
            .where(Investment.id == investment_id)
            .values(is_closed=0, closed_date=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_investment(self, investment_id: int) -> None:
        """Delete an investment by ID.

        Parameters
        ----------
        investment_id : int
            Primary key of the investment to delete.

        Raises
        ------
        EntityNotFoundException
            If no investment with the given ID exists.
        """
        stmt = delete(Investment).where(Investment.id == investment_id)
        result = self.db.execute(stmt)
        self.db.commit()

        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No investment found with ID {investment_id}"
            )
