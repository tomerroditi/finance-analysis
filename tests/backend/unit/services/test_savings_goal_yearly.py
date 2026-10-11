"""Unit tests for yearly savings: income minus spending, per calendar year.

Saving is measured, not earmarked: investing is saving, a withdrawal is neutral
until spent, income a goal's saved-into rule claims is left out together with
the bills that income pays, and a year can save less than nothing.
"""

from datetime import date

import pytest

from backend.errors import ValidationException
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.savings_goals import SavingsGoalService
from tests.backend.unit.services.savings_goal_helpers import (
    add_card_txn,
    add_txn,
    month_str,
    seed_surplus,
)


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


def _months_this_year(count: int) -> list[str]:
    """The last ``count`` months that fall in the current calendar year."""
    months = [month_str(offset) for offset in range(count)]
    year = str(date.today().year)
    return [m for m in months if m.startswith(year)]


def _year(result: dict, year: int) -> dict:
    """The yearly row for ``year``."""
    return next(row for row in result["years"] if row["year"] == year)


class TestWhatAYearSaved:
    """Each rule of the definition, one month at a time."""

    def test_income_minus_spending(self, db_session, service):
        """A month's saving is what it earned less what it spent."""
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 3000

    def test_investing_is_saving_and_a_withdrawal_is_neutral(
        self, db_session, service
    ):
        """Money moved into or out of an investment never changes the figure."""
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)
        add_txn(db_session, month, -5000, "Investments", tag="Pakam", day=3)
        add_txn(db_session, month, 2000, "Investments", tag="Pakam", day=20)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == 3000

    def test_spending_more_than_was_earned_saves_less_than_nothing(
        self, db_session, service
    ):
        """A withdrawal spent on living leaves a negative year."""
        month = month_str(0)
        seed_surplus(db_session, month, income=5000, expenses=9000)
        add_txn(db_session, month, 4000, "Investments", tag="Pakam", day=3)

        result = service.get_yearly_savings()

        assert _year(result, date.today().year)["saved"] == -4000

    def test_a_goals_own_income_and_the_bills_it_pays_are_left_out(
        self, db_session, service
    ):
        """Wedding gifts and the bills they pay are the goal's, not the year's."""
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)
        add_txn(db_session, month, 20000, "Other Income", tag="Wedding", day=4)
        add_txn(db_session, month, -15000, "Wedding", tag="Venue", day=9)
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
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)
        add_txn(db_session, month, 8000, "Other Income", tag="Wedding", day=4)
        add_txn(db_session, month, -10000, "Wedding", tag="Venue", day=9)
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
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)
        add_txn(db_session, month, -2000, "Travel", day=9)
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
            seed_surplus(db_session, month, income=10000 + amount, expenses=10000)

        row = _year(service.get_yearly_savings(), date.today().year)

        assert [m["month"] for m in row["months"]] == sorted(months)
        assert row["saved"] == sum(m["saved"] for m in row["months"])


def _month(result: dict, month: str) -> float:
    """What ``month`` saved, from whichever year lists it."""
    for row in result["years"]:
        for entry in row["months"]:
            if entry["month"] == month:
                return entry["saved"]
    return 0.0


class TestMatchesIncomeAndExpenses:
    """A year saves what the Income & Expenses card nets for it."""

    def test_moving_money_between_own_accounts_is_not_spending(
        self, db_session, service
    ):
        """An Ignore transfer out to an untracked account leaves the figure alone."""
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=7000)
        add_txn(db_session, month, -3000, "Ignore", tag="Internal Transactions", day=8)

        assert _month(service.get_yearly_savings(), month) == 3000

    def test_card_purchases_count_when_made_not_when_the_bill_is_paid(
        self, db_session, service
    ):
        """A purchase counts in its own month; the bank-side bill counts nowhere."""
        bought, billed = month_str(1), month_str(0)
        add_txn(db_session, bought, 10000, "Salary", day=1)
        add_card_txn(db_session, bought, -4000, "Food", day=20)
        add_txn(db_session, billed, -4000, "Credit Cards", day=2)

        result = service.get_yearly_savings()

        assert _month(result, bought) == 6000
        assert _month(result, billed) == 0

    def test_a_matched_refund_counts_against_its_purchase(self, db_session, service):
        """The refund comes off the purchase's month, not the month it landed in."""
        bought, refunded = month_str(1), month_str(0)
        purchase = add_txn(db_session, bought, -1000, "Health", day=5)
        refund = add_txn(db_session, refunded, 600, "Health", day=5)
        refunds = PendingRefundsService(db_session)
        pending = refunds.mark_as_pending_refund(
            source_type="transaction",
            source_id=purchase.unique_id,
            source_table="banks",
            expected_amount=600,
        )
        refunds.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=refund.unique_id,
            refund_source="banks",
            amount=600,
        )

        result = service.get_yearly_savings()

        assert _month(result, bought) == -400
        assert _month(result, refunded) == 0


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
        month = month_str(0)
        seed_surplus(db_session, month, income=10000, expenses=4000)
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
