"""Data access for savings goals."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.savings_goal import SavingsGoal


class SavingsGoalRepository:
    """Repository for ``savings_goals`` CRUD operations."""

    def __init__(self, db: Session):
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Return all savings goals as a DataFrame (empty with no rows)."""
        records = self.db.execute(select(SavingsGoal)).scalars().all()
        if not records:
            return pd.DataFrame(
                columns=["id", "name", "target_amount", "current_amount", "target_date", "notes"]
            )
        df = pd.DataFrame([r.__dict__ for r in records])
        return df.drop(columns=["_sa_instance_state"], errors="ignore")

    def get(self, goal_id: int) -> SavingsGoal | None:
        """Return a single goal by id, or None."""
        return self.db.get(SavingsGoal, goal_id)

    def add(self, **fields) -> SavingsGoal:
        """Insert a new goal and return the persisted row."""
        goal = SavingsGoal(**fields)
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update(self, goal_id: int, **fields) -> SavingsGoal:
        """Update an existing goal and return it."""
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise ValueError(f"No savings goal with id {goal_id}")
        for key, value in fields.items():
            if value is not None:
                setattr(goal, key, value)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def delete(self, goal_id: int) -> None:
        """Delete a goal by id."""
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise ValueError(f"No savings goal with id {goal_id}")
        self.db.delete(goal)
        self.db.commit()
