"""Business logic for savings goals.

Wraps the repository and enriches each goal with derived progress metrics —
percentage complete, remaining amount, and the monthly contribution needed to
hit the target by its date.
"""

import math

import pandas as pd
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.repositories.savings_goal_repository import SavingsGoalRepository


class SavingsGoalService:
    """Service for managing savings goals and computing progress."""

    def __init__(self, db: Session):
        """Initialize the service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = SavingsGoalRepository(db)

    def get_all(self) -> list[dict]:
        """Return all goals enriched with progress metrics.

        Returns
        -------
        list[dict]
            Goal dicts ordered by target date (goals without a date last).
        """
        df = self.repo.get_all()
        if df.empty:
            return []
        goals = [self._enrich(row._asdict()) for row in df.itertuples(index=False)]
        goals.sort(key=lambda g: (g["target_date"] is None, g["target_date"] or ""))
        return goals

    def create(self, **fields) -> dict:
        """Create a new savings goal."""
        goal = self.repo.add(**fields)
        return self._enrich(self._to_dict(goal))

    def update(self, goal_id: int, **fields) -> dict:
        """Update an existing savings goal."""
        try:
            goal = self.repo.update(goal_id, **fields)
        except ValueError:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        return self._enrich(self._to_dict(goal))

    def delete(self, goal_id: int) -> None:
        """Delete a savings goal."""
        try:
            self.repo.delete(goal_id)
        except ValueError:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")

    @staticmethod
    def _to_dict(goal) -> dict:
        return {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "current_amount": goal.current_amount,
            "target_date": goal.target_date,
            "notes": goal.notes,
        }

    @staticmethod
    def _enrich(goal: dict) -> dict:
        """Attach derived progress metrics to a goal dict."""
        target = float(goal.get("target_amount") or 0.0)
        current = float(goal.get("current_amount") or 0.0)
        remaining = max(0.0, target - current)
        progress_pct = round(min(100.0, (current / target * 100) if target > 0 else 0.0), 1)
        is_achieved = target > 0 and current >= target

        months_remaining = None
        monthly_needed = None
        target_date = goal.get("target_date")
        if target_date:
            today = pd.Timestamp.today().normalize()
            target_ts = pd.Timestamp(target_date)
            months = (target_ts.year - today.year) * 12 + (target_ts.month - today.month)
            months_remaining = max(0, int(months))
            if not is_achieved:
                monthly_needed = round(remaining / months_remaining, 2) if months_remaining > 0 else round(remaining, 2)

        return {
            **goal,
            "target_amount": round(target, 2),
            "current_amount": round(current, 2),
            "remaining": round(remaining, 2),
            "progress_pct": progress_pct,
            "is_achieved": is_achieved,
            "months_remaining": months_remaining,
            "monthly_needed": monthly_needed if monthly_needed is None or not math.isnan(monthly_needed) else None,
        }
