"""Unit tests for RetirementGoalRepository — single-row upsert pattern."""

from sqlalchemy import select

from backend.models.retirement_goal import RetirementGoal
from backend.repositories.retirement_goal_repository import (
    RetirementGoalRepository,
)


class TestRetirementGoalRepository:
    """Tests for the single-row retirement goal profile access."""

    def test_get_returns_none_when_empty(self, db_session):
        """A fresh DB has no retirement profile."""
        repo = RetirementGoalRepository(db_session)
        assert repo.get() is None

    def test_upsert_creates_profile(self, db_session):
        """First upsert inserts the single profile row."""
        repo = RetirementGoalRepository(db_session)

        goal = repo.upsert(
            current_age=35,
            gender="female",
            target_retirement_age=52,
            monthly_expenses_in_retirement=12000.0,
        )

        assert goal.id is not None
        assert goal.current_age == 35
        assert goal.gender == "female"
        stored = repo.get()
        assert stored is not None and stored.id == goal.id

    def test_upsert_updates_existing_row_in_place(self, db_session):
        """Second upsert mutates the existing row — never a second row."""
        repo = RetirementGoalRepository(db_session)
        first = repo.upsert(
            current_age=35, monthly_expenses_in_retirement=12000.0
        )

        second = repo.upsert(current_age=36, target_retirement_age=55)

        assert second.id == first.id
        assert second.current_age == 36
        assert second.target_retirement_age == 55
        # Unspecified fields survive the partial update.
        assert second.monthly_expenses_in_retirement == 12000.0
        rows = db_session.execute(select(RetirementGoal)).scalars().all()
        assert len(rows) == 1

    def test_delete_returns_true_and_removes_row(self, db_session):
        """delete removes the profile and reports success."""
        repo = RetirementGoalRepository(db_session)
        repo.upsert(current_age=35, monthly_expenses_in_retirement=12000.0)

        assert repo.delete() is True
        assert repo.get() is None

    def test_delete_returns_false_when_empty(self, db_session):
        """delete on an empty table is a no-op returning False."""
        repo = RetirementGoalRepository(db_session)
        assert repo.delete() is False
