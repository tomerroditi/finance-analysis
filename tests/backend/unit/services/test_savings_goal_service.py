"""Unit tests for SavingsGoalService — CRUD, lifecycle, and derived metrics.

The waterfall itself is covered in ``test_savings_goal_allocation.py``; these
tests use goals with an ``opening_balance`` and no transactions, so the
allocation engine contributes nothing and the enrichment maths is isolated.
"""

from datetime import date

import pandas as pd
import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.services.savings_goal_service import DAYS_PER_MONTH, SavingsGoalService


def _months_until(target_date: str) -> int:
    """Mirror the service's month-diff formula relative to today."""
    today = pd.Timestamp.today().normalize()
    target = pd.Timestamp(target_date)
    return max(0, (target.year - today.year) * 12 + (target.month - today.month))


def _runway_months_until(target_date: str) -> float:
    """Mirror the service's day-based runway relative to today.

    `months_remaining` (above) is a calendar-month difference that ignores
    the day of month; `monthly_needed` is deliberately sized off the real
    runway in days instead, so a goal due on the 1st two months out isn't
    treated as two full months when only ~39 days remain. The two are
    different quantities — asserting `monthly_needed` against the calendar
    count only agreed by rounding coincidence and broke the day the month
    ticked over (881 calendar months -> 880 while the day runway held).
    """
    today = pd.Timestamp.today().normalize()
    target = pd.Timestamp(target_date)
    return max(0, (target - today).days) / DAYS_PER_MONTH


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


def _only(goals: list[dict]) -> dict:
    """Return the single goal in a service response."""
    assert len(goals) == 1
    return goals[0]


class TestSavingsGoalServiceCrud:
    """Tests for create/update/delete/get_all behaviour."""

    def test_get_all_empty_returns_empty_list(self, service):
        """A fresh DB yields an empty list, not an empty DataFrame."""
        assert service.get_all() == []

    def test_create_persists_and_returns_enriched_goal(self, service):
        """A created goal comes back with its derived progress fields."""
        goal = _only(service.create(name="Vacation", target_amount=1000, opening_balance=250))

        assert goal["name"] == "Vacation"
        assert goal["funded"] == 250
        assert goal["remaining"] == 750
        assert goal["progress_pct"] == 25.0
        assert goal["is_achieved"] is False

    def test_create_defaults_priority_to_the_bottom(self, service):
        """Each new goal is appended to the end of the waterfall."""
        service.create(name="First", target_amount=1000)
        goals = service.create(name="Second", target_amount=1000)

        by_name = {g["name"]: g for g in goals}
        assert by_name["First"]["priority"] < by_name["Second"]["priority"]

    def test_create_defaults_start_month_to_this_month(self, service):
        """A new goal never claims surpluses from months that predate it."""
        goal = _only(service.create(name="Vacation", target_amount=1000))
        today = date.today()
        assert goal["start_month"] == f"{today.year:04d}-{today.month:02d}"

    def test_create_rejects_an_unparseable_start_month(self, service):
        """A malformed start month is refused rather than silently ignored."""
        with pytest.raises(ValidationException):
            service.create(name="Vacation", target_amount=1000, start_month="nope")

    def test_update_changes_fields(self, service):
        """Updating a goal restates its derived metrics."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        updated = _only(service.update(created["id"], target_amount=2000, name="Trip"))

        assert updated["name"] == "Trip"
        assert updated["target_amount"] == 2000

    def test_update_missing_raises_not_found(self, service):
        """Updating an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.update(9999, name="nope")

    def test_delete_removes_goal(self, service):
        """A deleted goal disappears from the list."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        service.delete(created["id"])

        assert service.get_all() == []

    def test_delete_missing_raises_not_found(self, service):
        """Deleting an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.delete(9999)

    def test_get_all_orders_by_priority(self, service):
        """Goals come back in waterfall order, not insertion order."""
        service.create(name="A", target_amount=100)
        service.create(name="B", target_amount=100)
        ids = {g["name"]: g["id"] for g in service.get_all()}

        service.reorder([ids["B"], ids["A"]])

        assert [g["name"] for g in service.get_all()] == ["B", "A"]

    def test_reorder_rejects_unknown_ids(self, service):
        """Reordering with an id that does not exist is refused."""
        created = _only(service.create(name="A", target_amount=100))
        with pytest.raises(EntityNotFoundException):
            service.reorder([created["id"], 9999])


class TestGoalLifecycle:
    """Tests for closing and reopening a goal by hand."""

    def test_close_marks_the_goal_and_stamps_the_month(self, service):
        """Closing freezes a goal and records when it happened."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        closed = _only(service.close(created["id"]))

        today = date.today()
        assert closed["is_closed"] is True
        assert closed["closed_month"] == f"{today.year:04d}-{today.month:02d}"

    def test_reopen_clears_the_closed_state(self, service):
        """A reopened goal absorbs surplus again."""
        created = _only(service.create(name="Vacation", target_amount=1000))
        service.close(created["id"])

        reopened = _only(service.reopen(created["id"]))

        assert reopened["is_closed"] is False
        assert reopened["closed_month"] is None

    def test_close_missing_raises_not_found(self, service):
        """Closing an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.close(9999)


class TestSavingsGoalEnrichment:
    """Tests for the derived progress metrics attached to each goal."""

    def test_zero_target_yields_zero_progress(self, db_session, service):
        """A zero target can't divide, so progress stays at 0 rather than NaN."""
        from backend.models.savings_goal import SavingsGoal

        db_session.add(SavingsGoal(name="Zero", target_amount=0, opening_balance=100))
        db_session.commit()

        goal = _only(service.get_all())
        assert goal["progress_pct"] == 0.0
        assert goal["is_achieved"] is False

    def test_overshoot_caps_progress_at_100(self, service):
        """Saving past the target caps the bar without capping the amount."""
        goal = _only(service.create(name="Over", target_amount=1000, opening_balance=1500))

        assert goal["progress_pct"] == 100.0
        assert goal["funded"] == 1500
        assert goal["remaining"] == 0
        assert goal["is_achieved"] is True

    def test_future_target_date_sets_monthly_needed(self, service):
        """A dated goal reports the contribution needed over its real runway."""
        target_date = (pd.Timestamp.today().normalize() + pd.DateOffset(months=5)).strftime(
            "%Y-%m-%d"
        )
        goal = _only(
            service.create(
                name="Trip", target_amount=1000, opening_balance=0, target_date=target_date
            )
        )

        assert goal["months_remaining"] == _months_until(target_date)
        assert goal["monthly_needed"] == pytest.approx(
            round(1000 / _runway_months_until(target_date), 2)
        )

    def test_past_target_date_needs_full_remaining_now(self, service):
        """An overdue goal asks for everything that is left, immediately."""
        past = (pd.Timestamp.today().normalize() - pd.DateOffset(months=2)).strftime(
            "%Y-%m-%d"
        )
        goal = _only(
            service.create(
                name="Late", target_amount=1000, opening_balance=200, target_date=past
            )
        )

        assert goal["months_remaining"] == 0
        assert goal["monthly_needed"] == 800

    def test_achieved_goal_has_no_monthly_needed(self, service):
        """Nothing more is needed once the target is met."""
        future = (pd.Timestamp.today().normalize() + pd.DateOffset(months=3)).strftime(
            "%Y-%m-%d"
        )
        goal = _only(
            service.create(
                name="Done", target_amount=1000, opening_balance=1000, target_date=future
            )
        )

        assert goal["is_achieved"] is True
        assert goal["monthly_needed"] is None

    def test_no_target_date_has_no_time_metrics(self, service):
        """A dateless goal reports progress but no schedule."""
        goal = _only(service.create(name="Someday", target_amount=1000, opening_balance=100))

        assert goal["months_remaining"] is None
        assert goal["monthly_needed"] is None


class TestRunwayUsesRealDays:
    """`monthly_needed` is sized off days remaining, not whole calendar months."""

    def test_monthly_needed_accounts_for_partial_first_month(self, service):
        """A goal due early next month asks for more than a naive month split."""
        target_ts = (pd.Timestamp.today().normalize() + pd.DateOffset(months=2)).replace(day=1)
        target_date = target_ts.strftime("%Y-%m-%d")
        goal = _only(
            service.create(
                name="Soon", target_amount=1000, opening_balance=0, target_date=target_date
            )
        )

        runway = _runway_months_until(target_date)
        assert goal["monthly_needed"] == pytest.approx(round(1000 / runway, 2))
        # The calendar-month count would understate the required contribution.
        assert goal["monthly_needed"] > 1000 / max(1, _months_until(target_date))

    def test_achieved_goal_has_no_monthly_needed(self, service):
        """An achieved goal skips the runway maths entirely."""
        target_ts = (pd.Timestamp.today().normalize() + pd.DateOffset(months=2)).replace(day=1)
        goal = _only(
            service.create(
                name="Soon",
                target_amount=1000,
                opening_balance=1200,
                target_date=target_ts.strftime("%Y-%m-%d"),
            )
        )

        assert goal["monthly_needed"] is None
