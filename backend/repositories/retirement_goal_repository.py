"""
RetirementGoal data access.

Single-row upsert pattern — only one retirement goal profile per user.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.retirement_goal import RetirementGoal


class RetirementGoalRepository:
    """RetirementGoal database operations (single-row upsert)."""

    def __init__(self, db: Session):
        self.db = db

    def get(self) -> RetirementGoal | None:
        """Get the retirement goal profile (single row)."""
        stmt = select(RetirementGoal)
        return self.db.execute(stmt).scalars().first()

    def upsert(self, **fields) -> RetirementGoal:
        """Create or update the retirement goal profile.

        Parameters
        ----------
        **fields
            Column values to set on the RetirementGoal record.

        Returns
        -------
        RetirementGoal
            The created or updated record.
        """
        existing = self.get()
        if existing:
            for key, value in fields.items():
                if value is not None:
                    setattr(existing, key, value)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        item = RetirementGoal(**fields)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self) -> bool:
        """Delete the retirement goal profile."""
        item = self.get()
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        return True
