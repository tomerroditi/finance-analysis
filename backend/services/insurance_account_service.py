"""
Insurance account business logic.

Provides access to insurance account metadata (pension, keren hishtalmut)
and derived calculations like total balances.
"""

from sqlalchemy.orm import Session

from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)


class InsuranceAccountService:
    """Insurance account queries and balance aggregations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = InsuranceAccountRepository(db)

    def get_all(self) -> list[dict]:
        """Get all insurance account records as dicts."""
        accounts = self.repo.get_all()
        return [self._to_dict(a) for a in accounts]

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

    @staticmethod
    def _to_dict(account) -> dict:
        """Convert an InsuranceAccount ORM instance to a dict."""
        return {
            "id": account.id,
            "provider": account.provider,
            "policy_id": account.policy_id,
            "policy_type": account.policy_type,
            "pension_type": account.pension_type,
            "account_name": account.account_name,
            "balance": account.balance,
            "balance_date": account.balance_date,
            "investment_tracks": account.investment_tracks,
            "commission_deposits_pct": account.commission_deposits_pct,
            "commission_savings_pct": account.commission_savings_pct,
            "insurance_covers": account.insurance_covers,
            "insurance_costs": account.insurance_costs,
            "liquidity_date": account.liquidity_date,
        }
