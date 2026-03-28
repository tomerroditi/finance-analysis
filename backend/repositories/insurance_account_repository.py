"""
InsuranceAccount data access.

CRUD operations for insurance account metadata (pension, keren hishtalmut, gemel).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.insurance_account import InsuranceAccount


class InsuranceAccountRepository:
    """InsuranceAccount database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[InsuranceAccount]:
        """Get all insurance account records."""
        stmt = select(InsuranceAccount)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_policy_type(self, policy_type: str) -> list[InsuranceAccount]:
        """Get insurance accounts filtered by policy type.

        Parameters
        ----------
        policy_type : str
            One of: ``pension``, ``hishtalmut``.
        """
        stmt = select(InsuranceAccount).where(
            InsuranceAccount.policy_type == policy_type
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_policy_id(self, policy_id: str) -> InsuranceAccount | None:
        """Get a single insurance account by its policy ID."""
        stmt = select(InsuranceAccount).where(
            InsuranceAccount.policy_id == policy_id
        )
        return self.db.execute(stmt).scalars().first()

    def upsert(self, **fields) -> InsuranceAccount:
        """Create or update an insurance account by policy_id.

        Parameters
        ----------
        **fields
            Column values; must include ``policy_id``.

        Returns
        -------
        InsuranceAccount
            The created or updated record.
        """
        policy_id = fields.get("policy_id")
        if not policy_id:
            raise ValueError("policy_id is required for upsert")
        existing = self.get_by_policy_id(policy_id)
        if existing:
            for key, value in fields.items():
                if key != "policy_id":
                    setattr(existing, key, value)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        item = InsuranceAccount(**fields)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
