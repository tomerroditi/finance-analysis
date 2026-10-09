"""Unit tests for yearly savings: income minus spending, per calendar year.

Saving is measured, not earmarked: investing is saving, a withdrawal is neutral
until spent, income a goal's saved-into rule claims is left out together with
the bills that income pays, and a year can save less than nothing.
"""

from datetime import date

import pytest

from backend.errors import ValidationException
from backend.services.savings_goals import SavingsGoalService
from tests.backend.unit.services.test_savings_goal_allocation import (
    _add_txn,
    _month_str,
    _seed_surplus,
)


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


def _months_this_year(count: int) -> list[str]:
    """The last ``count`` months that fall in the current calendar year."""
    months = [_month_str(offset) for offset in range(count)]
    year = str(date.today().year)
    return [m for m in months if m.startswith(year)]


def _year(result: dict, year: int) -> dict:
    """The yearly row for ``year``."""
    return next(row for row in result["years"] if row["year"] == year)


class TestWhatAYearSaved:
    """Each rule of the definition, one month at a time."""

    def test_income_minus_spending(self, db_session, service):
        """A month's saving is what it earned less what it spent."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=7000)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 3000

    def test_investing_is_saving_and_a_withdrawal_is_neutral(
        self, db_session, service
    ):
        """Money moved into or out of an investment never changes the figure."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        _add_txn(db_session, month, -5000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, month, 2000, "Investments", tag="Pakam", day=20)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 3000

    def test_spending_more_than_was_earned_saves_less_than_nothing(
        self, db_session, service
    ):
        """A withdrawal spent on living leaves a negative year."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=5000, expenses=9000)
        _add_txn(db_session, month, 4000, "Investments", tag="Pakam", day=3)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == -4000

    def test_a_goals_own_income_and_the_bills_it_pays_are_left_out(
        self, db_session, service
    ):
        """Wedding gifts and the bills they pay are the goal's, not the year's."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        _add_txn(db_session, month, 20000, "Other Income", tag="Wedding", day=4)
        _add_txn(db_session, month, -15000, "Wedding", tag="Venue", day=9)
        service.create(
            name="Wedding",
            target_amount=20000,
            start_month=month,
            contribution_category="Other Income",
            contribution_tags="Wedding",
            utilization_category="Wedding",
        )

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 3000

    def test_bills_beyond_a_goals_income_are_the_households_spending(
        self, db_session, service
    ):
        """What the gifts did not cover came out of the household's own money."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        _add_txn(db_session, month, 8000, "Other Income", tag="Wedding", day=4)
        _add_txn(db_session, month, -10000, "Wedding", tag="Venue", day=9)
        service.create(
            name="Wedding",
            target_amount=20000,
            start_month=month,
            contribution_category="Other Income",
            contribution_tags="Wedding",
            utilization_category="Wedding",
        )

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 1000

    def test_spending_out_of_savings_is_spending(self, db_session, service):
        """A trip paid from a goal without income of its own is spent this year."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        _add_txn(db_session, month, -2000, "Travel", day=9)
        service.create(
            name="Trip",
            target_amount=5000,
            start_month=month,
            utilization_category="Travel",
        )

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 1000

    def test_months_are_reported_and_add_up_to_the_year(self, db_session, service):
        """Each month on record is listed, and they sum to the year's figure."""
        months = _months_this_year(3)
        for amount, month in zip((1000, 2000, -500), months, strict=False):
            _seed_surplus(db_session, month, income=10000 + amount, expenses=10000)

        row = _year(service.get_yearly_savings(), date.today().year)

        assert [m["month"] for m in row["months"]] == sorted(months)
        assert row["saved"] == sum(m["saved"] for m in row["months"])


class TestYearlyTargets:
    """One target per year, and where an even pace toward it stands today."""

    def test_no_target_means_no_pace(self, db_session, service):
        """Without a target there is nothing to pace against."""
        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["target"] is None
        assert result["pace"] is None

    def test_a_target_is_kept_per_year(self, db_session, service):
        """Setting this year's target leaves last year's alone."""
        this_year = date.today().year
        service.set_yearly_target(this_year - 1, 80000)
        result = service.set_yearly_target(this_year, 120000)

        assert _year(result, this_year)["target"] == 120000
        assert _year(result, this_year - 1)["target"] == 80000

        cleared = service.set_yearly_target(this_year, None)
        assert _year(cleared, this_year)["target"] is None

    def test_pace_compares_saved_with_an_even_share_of_the_target(
        self, db_session, service
    ):
        """Expected-by-today is the elapsed share; needed is what is left per month."""
        month = _month_str(0)
        _seed_surplus(db_session, month, income=10000, expenses=4000)
        today = date.today()
        start = date(today.year, 1, 1)
        share = ((today - start).days + 1) / (date(today.year + 1, 1, 1) - start).days

        pace = service.set_yearly_target(today.year, 120000)["pace"]

        assert pace["expected_by_today"] == pytest.approx(120000 * share, abs=0.01)
        assert pace["ahead_by"] == pytest.approx(6000 - 120000 * share, abs=0.01)
        assert pace["months_left"] == 12 - today.month + 1
        assert pace["needed_per_month"] == pytest.approx(
            (120000 - 6000) / pace["months_left"], abs=0.01
        )

    def test_a_target_must_be_positive(self, service):
        """Zero or a negative amount is not a target."""
        with pytest.raises(ValidationException):
            service.set_yearly_target(date.today().year, 0)
