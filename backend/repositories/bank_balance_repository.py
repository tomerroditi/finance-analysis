"""
Bank balance repository for account balance snapshots.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance


class BankBalanceRepository:
    """Repository for bank account balance snapshots."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all bank balance records.

        Returns
        -------
        pd.DataFrame
            All balance records with columns: id, provider, account_name,
            balance, prior_wealth_amount, last_manual_update, last_scrape_update.
        """
        stmt = select(BankBalance)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_account(self, provider: str, account_name: str) -> BankBalance | None:
        """Get balance record for a specific account.

        Parameters
        ----------
        provider : str
            Bank provider name to filter by.
        account_name : str
            Account display name to filter by.

        Returns
        -------
        BankBalance | None
            The matching ORM record, or None if not found.
        """
        stmt = select(BankBalance).where(
            BankBalance.provider == provider,
            BankBalance.account_name == account_name,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        provider: str,
        account_name: str,
        balance: float,
        prior_wealth_amount: float,
        last_manual_update: str | None = None,
        last_scrape_update: str | None = None,
    ) -> BankBalance:
        """Create or update a balance record for an account.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            Account display name.
        balance : float
            Current account balance.
        prior_wealth_amount : float
            Prior wealth amount associated with this account.
        last_manual_update : str | None
            ISO date of the last manual balance entry, or None.
        last_scrape_update : str | None
            ISO date of the last scraped update, or None.

        Returns
        -------
        BankBalance
            The created or updated ORM record.
        """
        existing = self.get_by_account(provider, account_name)
        if existing:
            existing.balance = balance
            existing.prior_wealth_amount = prior_wealth_amount
            if last_manual_update is not None:
                existing.last_manual_update = last_manual_update
            if last_scrape_update is not None:
                existing.last_scrape_update = last_scrape_update
            self.db.commit()
            return existing
        else:
            record = BankBalance(
                provider=provider,
                account_name=account_name,
                balance=balance,
                prior_wealth_amount=prior_wealth_amount,
                last_manual_update=last_manual_update,
                last_scrape_update=last_scrape_update,
            )
            self.db.add(record)
            self.db.commit()
            return record

    def delete_by_account(self, provider: str, account_name: str) -> bool:
        """Delete balance record for an account.

        Parameters
        ----------
        provider : str
            Bank provider name to match.
        account_name : str
            Account display name to match.

        Returns
        -------
        bool
            True if a record was found and deleted, False if not found.
        """
        existing = self.get_by_account(provider, account_name)
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False
