"""
Insurance account business logic.

Provides access to insurance account metadata (pension, keren hishtalmut)
and derived calculations like total balances.
"""

from sqlalchemy.orm import Session

from backend.models.insurance_account import InsuranceAccount
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
