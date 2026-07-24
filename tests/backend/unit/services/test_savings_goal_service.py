"""Unit tests for SavingsGoalService — CRUD and derived progress metrics."""

import pandas as pd
import pytest

from backend.errors import EntityNotFoundException
from backend.models.savings_goal import SavingsGoal
from backend.services.savings_goal_service import SavingsGoalService


def _months_until(target_date: str) -> int:
    """Mirror the service's month-diff formula relative to today."""
    today = pd.Timestamp.today().normalize()
    target = pd.Timestamp(target_date)
    return max(0, (target.year - today.year) * 12 + (target.month - today.month))


class TestSavingsGoalServiceCrud:
    """Tests for create/update/delete/get_all behaviour."""

    def test_get_all_empty_returns_empty_list(self, db_session):
        """A fresh DB yields an empty list, not an empty DataFrame."""
        service = SavingsGoalService(db_session)
        assert service.get_all() == []

    def test_create_persists_and_returns_enriched_goal(self, db_session):
        """create stores the goal and returns it with progress metrics."""
        service = SavingsGoalService(db_session)

        goal = service.create(
            name="Vacation", target_amount=10000.0, current_amount=2500.0
        )

        assert goal["name"] == "Vacation"
        assert goal["progress_pct"] == 25.0
        assert goal["remaining"] == 7500.0
        assert goal["is_achieved"] is False
        stored = db_session.get(SavingsGoal, goal["id"])
        assert stored is not None and stored.target_amount == 10000.0

    def test_update_changes_fields(self, db_session):
        """update mutates the stored goal and re-enriches the response."""
        service = SavingsGoalService(db_session)
        goal = service.create(name="Fund", target_amount=5000.0, current_amount=0.0)

        updated = service.update(goal["id"], current_amount=5000.0)

        assert updated["is_achieved"] is True
        assert updated["progress_pct"] == 100.0
        assert updated["remaining"] == 0.0
        stored = db_session.get(SavingsGoal, goal["id"])
        assert stored.current_amount == 5000.0

    def test_update_missing_raises_not_found(self, db_session):
        """Updating a nonexistent goal raises EntityNotFoundException."""
        service = SavingsGoalService(db_session)
        with pytest.raises(EntityNotFoundException, match="not found"):
            service.update(9999, current_amount=1.0)

    def test_delete_removes_goal(self, db_session):
        """delete removes the goal row from the DB."""
        service = SavingsGoalService(db_session)
        goal = service.create(name="Temp", target_amount=100.0)

        service.delete(goal["id"])

        assert service.get_all() == []
        assert db_session.get(SavingsGoal, goal["id"]) is None

    def test_delete_missing_raises_not_found(self, db_session):
        """Deleting a nonexistent goal raises EntityNotFoundException."""
        service = SavingsGoalService(db_session)
        with pytest.raises(EntityNotFoundException, match="not found"):
            service.delete(9999)

    def test_get_all_orders_by_target_date_with_none_last(self, db_session):
        """Goals sort by target date ascending; undated goals come last."""
        service = SavingsGoalService(db_session)
        service.create(name="No Date", target_amount=100.0)
        service.create(name="Later", target_amount=100.0, target_date="2099-06-01")
        service.create(name="Sooner", target_amount=100.0, target_date="2098-01-01")

        names = [g["name"] for g in service.get_all()]

        assert names == ["Sooner", "Later", "No Date"]


class TestSavingsGoalEnrichment:
    """Tests for the derived progress metrics attached to each goal."""

    def test_zero_target_yields_zero_progress(self, db_session):
        """A zero target cannot divide — progress is 0 and never achieved."""
        service = SavingsGoalService(db_session)
        goal = service.create(name="Empty", target_amount=0.0, current_amount=50.0)

        assert goal["progress_pct"] == 0.0
        assert goal["is_achieved"] is False
        assert goal["remaining"] == 0.0

    def test_overshoot_caps_progress_at_100(self, db_session):
        """Saving beyond the target caps progress_pct at 100."""
        service = SavingsGoalService(db_session)
        goal = service.create(
            name="Over", target_amount=1000.0, current_amount=1500.0
        )

        assert goal["progress_pct"] == 100.0
        assert goal["is_achieved"] is True
        assert goal["remaining"] == 0.0

    def test_future_target_date_sets_monthly_needed(self, db_session):
        """A future target date yields months_remaining and a monthly figure."""
        service = SavingsGoalService(db_session)
        target_date = "2099-12-31"
        goal = service.create(
            name="Car",
            target_amount=12000.0,
            current_amount=0.0,
            target_date=target_date,
        )

        months = _months_until(target_date)
        assert goal["months_remaining"] == months
        assert goal["monthly_needed"] == round(12000.0 / months, 2)

    def test_past_target_date_needs_full_remaining_now(self, db_session):
        """A past target date leaves 0 months and the full remaining amount."""
        service = SavingsGoalService(db_session)
        goal = service.create(
            name="Late",
            target_amount=800.0,
            current_amount=300.0,
            target_date="2020-01-01",
        )

        assert goal["months_remaining"] == 0
        assert goal["monthly_needed"] == 500.0

    def test_achieved_goal_has_no_monthly_needed(self, db_session):
        """An achieved goal has no contribution requirement, even with a date."""
        service = SavingsGoalService(db_session)
        goal = service.create(
            name="Done",
            target_amount=1000.0,
            current_amount=1000.0,
            target_date="2099-12-31",
        )

        assert goal["is_achieved"] is True
        assert goal["monthly_needed"] is None
        assert goal["months_remaining"] == _months_until("2099-12-31")

    def test_no_target_date_has_no_time_metrics(self, db_session):
        """Without a target date both time-based metrics stay None."""
        service = SavingsGoalService(db_session)
        goal = service.create(name="Open", target_amount=1000.0)

        assert goal["months_remaining"] is None
        assert goal["monthly_needed"] is None


class TestRunwayUsesRealDays:
    """monthly_needed reflects the days actually remaining, not whole months."""

    def test_monthly_needed_accounts_for_partial_first_month(self, db_session):
        """A goal due on the 1st two calendar months out is not 2 full months.

        A pure calendar-month difference treated ~39 days of runway as two
        months, advising roughly two-thirds of the contribution required.
        """
        import pandas as pd

        today = pd.Timestamp.today().normalize()
        target = (today + pd.DateOffset(months=2)).replace(day=1)
        days_remaining = (target - today).days

        goal = SavingsGoalService(db_session).create(
            name="Trip", target_amount=12000.0, current_amount=0.0,
            target_date=target.strftime("%Y-%m-%d"),
        )

        required = 12000.0 / (days_remaining / 30.44)
        assert goal["monthly_needed"] == pytest.approx(required, abs=0.01)

    def test_achieved_goal_has_no_monthly_needed(self, db_session):
        """A goal already met reports no required contribution."""
        import pandas as pd

        target = (pd.Timestamp.today().normalize() + pd.DateOffset(months=2))
        goal = SavingsGoalService(db_session).create(
            name="Done", target_amount=100.0, current_amount=100.0,
            target_date=target.strftime("%Y-%m-%d"),
        )
        assert goal["is_achieved"] is True
        assert goal["monthly_needed"] is None
