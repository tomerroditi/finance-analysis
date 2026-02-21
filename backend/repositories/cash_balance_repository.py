"""
Cash balance repository for cash envelope balance snapshots.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.cash_balance import CashBalance


class CashBalanceRepository:
    """Repository for cash envelope balance snapshots."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all cash balance records.

        Returns
        -------
        pd.DataFrame
            All balance records with columns: id, account_name,
            balance, prior_wealth_amount, last_manual_update.
        """
        stmt = select(CashBalance)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_account_name(self, account_name: str) -> CashBalance | None:
        """Get balance record for a specific cash account.

        Parameters
        ----------
        account_name : str
            Account display name to filter by.

        Returns
        -------
        CashBalance | None
            The matching ORM record, or None if not found.
        """
        stmt = select(CashBalance).where(CashBalance.account_name == account_name)
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        account_name: str,
        balance: float,
        prior_wealth_amount: float,
        last_manual_update: str | None = None,
    ) -> CashBalance:
        """Create or update a balance record for a cash account.

        Parameters
        ----------
        account_name : str
            Account display name.
        balance : float
            Current cash balance.
        prior_wealth_amount : float
            Prior wealth amount associated with this cash account.
        last_manual_update : str | None
            ISO date of the last manual balance entry, or None.

        Returns
        -------
        CashBalance
            The created or updated ORM record.
        """
        existing = self.get_by_account_name(account_name)
        if existing:
            existing.balance = balance
            existing.prior_wealth_amount = prior_wealth_amount
            if last_manual_update is not None:
                existing.last_manual_update = last_manual_update
            self.db.commit()
            return existing
        else:
            record = CashBalance(
                account_name=account_name,
                balance=balance,
                prior_wealth_amount=prior_wealth_amount,
                last_manual_update=last_manual_update,
            )
            self.db.add(record)
            self.db.commit()
            return record

    def delete_by_account_name(self, account_name: str) -> bool:
        """Delete balance record for a cash account.

        Parameters
        ----------
        account_name : str
            Account display name to match.

        Returns
        -------
        bool
            True if a record was found and deleted, False if not found.
        """
        existing = self.get_by_account_name(account_name)
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False
