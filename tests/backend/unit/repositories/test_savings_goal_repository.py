"""Unit tests for SavingsGoalRepository CRUD operations."""

import pytest

from backend.models.savings_goal import SavingsGoal
from backend.repositories.savings_goal_repository import SavingsGoalRepository


class TestSavingsGoalRepository:
    """Tests for savings_goals data access."""

    def test_get_all_empty_returns_dataframe_with_columns(self, db_session):
        """An empty table still yields the canonical column schema."""
        repo = SavingsGoalRepository(db_session)

        df = repo.get_all()

        assert df.empty
        for col in [
            "id", "name", "target_amount", "current_amount", "target_date", "notes",
        ]:
            assert col in df.columns

    def test_add_persists_goal(self, db_session):
        """add inserts the row and returns the refreshed ORM object."""
        repo = SavingsGoalRepository(db_session)

        goal = repo.add(name="Vacation", target_amount=10000.0, current_amount=100.0)

        assert goal.id is not None
        df = repo.get_all()
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Vacation"

    def test_get_returns_goal_or_none(self, db_session):
        """get returns the row by id, or None for an unknown id."""
        repo = SavingsGoalRepository(db_session)
        goal = repo.add(name="Fund", target_amount=500.0)

        assert repo.get(goal.id).name == "Fund"
        assert repo.get(9999) is None

    def test_update_sets_fields(self, db_session):
        """update writes the provided fields to the row."""
        repo = SavingsGoalRepository(db_session)
        goal = repo.add(name="Fund", target_amount=500.0, current_amount=0.0)

        updated = repo.update(goal.id, current_amount=250.0, notes="halfway")

        assert updated.current_amount == 250.0
        assert updated.notes == "halfway"
        assert db_session.get(SavingsGoal, goal.id).current_amount == 250.0

    def test_update_ignores_none_values(self, db_session):
        """None fields are skipped so partial updates don't null-out columns."""
        repo = SavingsGoalRepository(db_session)
        goal = repo.add(name="Fund", target_amount=500.0, notes="keep me")

        updated = repo.update(goal.id, target_amount=600.0, notes=None)

        assert updated.target_amount == 600.0
        assert updated.notes == "keep me"

    def test_update_missing_raises_value_error(self, db_session):
        """Updating an unknown id raises ValueError."""
        repo = SavingsGoalRepository(db_session)
        with pytest.raises(ValueError, match="No savings goal"):
            repo.update(9999, target_amount=1.0)

    def test_delete_removes_goal(self, db_session):
        """delete removes the row from the table."""
        repo = SavingsGoalRepository(db_session)
        goal = repo.add(name="Temp", target_amount=1.0)

        repo.delete(goal.id)

        assert repo.get(goal.id) is None
        assert repo.get_all().empty

    def test_delete_missing_raises_value_error(self, db_session):
        """Deleting an unknown id raises ValueError."""
        repo = SavingsGoalRepository(db_session)
        with pytest.raises(ValueError, match="No savings goal"):
            repo.delete(9999)
