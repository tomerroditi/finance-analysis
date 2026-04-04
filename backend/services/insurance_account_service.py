"""
Insurance account business logic.

Provides access to insurance account metadata (pension, keren hishtalmut)
and derived calculations like total balances.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.insurance_account import InsuranceAccount
from backend.models.transaction import InsuranceTransaction
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)


class InsuranceAccountService:
    """Insurance account queries and balance aggregations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = InsuranceAccountRepository(db)

    def get_all(self) -> list[InsuranceAccount]:
        """Get all insurance account records."""
        return self.repo.get_all()

    def upsert(self, **fields) -> InsuranceAccount:
        """Create or update an insurance account by policy_id.

        Parameters
        ----------
        **fields
            Column values; must include ``policy_id``.
        """
        return self.repo.upsert(**fields)

    def get_keren_hishtalmut_balance(self) -> float | None:
        """Get total Keren Hishtalmut balance from scraped insurance data.

        Returns
        -------
        float or None
            Sum of all hishtalmut account balances, or None if no data.
        """
        accounts = self.repo.get_by_policy_type("hishtalmut")
        if not accounts:
            return None
        total = sum(a.balance for a in accounts if a.balance is not None)
        return total if total > 0 else None

    def get_monthly_contribution_by_type(
        self, policy_type: str
    ) -> float | None:
        """Get estimated monthly contribution for a policy type.

        Finds all accounts of the given type, checks which are active
        (have a transaction in the current or previous month), and sums
        the last transaction amount for each active account.

        Parameters
        ----------
        policy_type : str
            One of ``pension`` or ``hishtalmut``.

        Returns
        -------
        float or None
            Total monthly contribution across active accounts, or None
            if no active accounts exist.
        """
        accounts = self.repo.get_by_policy_type(policy_type)
        if not accounts:
            return None

        # Determine the cutoff: first day of previous month
        today = date.today()
        first_of_this_month = today.replace(day=1)
        first_of_prev_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
        cutoff = first_of_prev_month.isoformat()

        total = 0.0
        found_active = False

        for account in accounts:
            # Get the latest transaction for this account (by policy_id = account_number)
            stmt = (
                select(InsuranceTransaction)
                .where(InsuranceTransaction.account_number == account.policy_id)
                .order_by(InsuranceTransaction.date.desc())
                .limit(1)
            )
            latest_txn = self.db.execute(stmt).scalars().first()

            if latest_txn is None:
                continue

            # Active = latest transaction date >= first of previous month
            if latest_txn.date >= cutoff:
                found_active = True
                total += abs(latest_txn.amount)

        return total if found_active else None
