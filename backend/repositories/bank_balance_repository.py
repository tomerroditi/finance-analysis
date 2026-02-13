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
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all bank balance records."""
        stmt = select(BankBalance)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_account(self, provider: str, account_name: str) -> BankBalance | None:
        """Get balance record for a specific account."""
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
        """Create or update a balance record for an account."""
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
        """Delete balance record for an account. Returns True if deleted."""
        existing = self.get_by_account(provider, account_name)
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False
