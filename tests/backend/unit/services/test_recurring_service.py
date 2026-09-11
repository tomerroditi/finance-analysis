"""Tests for RecurringService subscription detection."""

import pandas as pd

from backend.constants.tables import Tables
from backend.models.transaction import CreditCardTransaction
from backend.services.recurring_service import RecurringService


def _add_charge(
    db_session, description, amount, date, category="Streaming",
    account_name="card-1",
):
    """Insert one itemized credit-card charge."""
    db_session.add(
        CreditCardTransaction(
            id=f"{description}-{account_name}-{date}-{amount}",
            date=date,
            provider="visa",
            account_name=account_name,
            description=description,
            amount=amount,
            category=category,
            source=Tables.CREDIT_CARD.value,
        )
    )


def _months_ago(n: int) -> str:
    """Return a YYYY-MM-DD string n months before today, on a fixed day.

    The day is capped at today's day-of-month so that ``_months_ago(0)`` can
    never land in the future — a charge dated ahead of "today" makes the
    ``new`` / ``ended`` verdicts nonsense for the first nine days of every
    month.
    """
    today = pd.Timestamp.today().normalize()
    day = min(10, today.day)
    d = (today - pd.DateOffset(months=n)).replace(day=day)
    return d.strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    """Return a YYYY-MM-DD string exactly n days before today."""
    return (pd.Timestamp.today().normalize() - pd.Timedelta(days=n)).strftime(
        "%Y-%m-%d"
    )


def _day_after_last_charge() -> pd.Timestamp:
    """Pin "today" one day past the newest ``_months_ago(0)`` charge.

    Every status verdict is measured against a reference day, and the
    ``new`` cut-off (age of the first charge vs. three periods) lands exactly
    on a month boundary for a four-month history. Pinning the reference makes
    the verdict independent of which month the suite happens to run in.
    """
    return pd.Timestamp(_months_ago(0)) + pd.Timedelta(days=1)


class TestRecurringDetection:
    """Tests for RecurringService.get_recurring."""

    def test_empty_db(self, db_session):
        """No transactions yields an empty, well-shaped result."""
        result = RecurringService(db_session).get_recurring()
        assert result == {"items": [], "total_monthly": 0.0}

    def test_detects_monthly_subscription(self, db_session):
        """A charge repeating monthly across 5 months is detected as monthly."""
        for n in range(5):
            _add_charge(db_session, "NETFLIX.COM 1234", -45.0, _months_ago(n))
        db_session.commit()

        result = RecurringService(db_session).get_recurring()
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["cadence"] == "monthly"
        assert item["amount"] == 45.0
        assert item["occurrences"] == 5
        assert item["monthly_equivalent"] == 45.0
        assert result["total_monthly"] == 45.0

    def test_ignores_one_off_charges(self, db_session):
        """Charges that appear fewer than three times are not recurring."""
        _add_charge(db_session, "RANDOM SHOP", -120.0, _months_ago(1))
        _add_charge(db_session, "ANOTHER SHOP", -80.0, _months_ago(2))
        db_session.commit()

        result = RecurringService(db_session).get_recurring()
        assert result["items"] == []

    def test_flags_new_subscription(self, db_session):
        """A subscription that only started recently is flagged ``new``."""
        for n in range(3):  # months 0,1,2 → first occurrence ~2 months ago
            _add_charge(db_session, "SPOTIFY AB", -20.0, _months_ago(n))
        db_session.commit()

        item = RecurringService(db_session).get_recurring()["items"][0]
        assert item["status"] == "new"

    def test_flags_price_increase(self, db_session):
        """A latest charge well above the prior median is flagged price_changed."""
        # Four contiguous months at 30 put the first charge well past the
        # "new" window (three periods), so the verdict is about the price.
        for n in range(4, 0, -1):
            _add_charge(db_session, "GYM CLUB", -30.0, _months_ago(n))
        _add_charge(db_session, "GYM CLUB", -45.0, _months_ago(0))  # latest hiked
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )["items"][0]
        assert item["status"] == "price_changed"
        assert item["price_change"] == 15.0
        assert item["occurrences"] == 5

    def test_flags_price_decrease(self, db_session):
        """A latest charge well below the prior median is flagged too, signed down.

        A cheaper renewal is still a change the insights engine surfaces, and
        the signed ``price_change`` is what tells the two apart.
        """
        for n in range(4, 0, -1):
            _add_charge(db_session, "GYM CLUB", -30.0, _months_ago(n))
        _add_charge(db_session, "GYM CLUB", -20.0, _months_ago(0))
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )["items"][0]
        assert item["status"] == "price_changed"
        assert item["price_change"] == -10.0
        assert item["last_amount"] == 20.0

    def test_detects_quarterly_subscription(self, db_session):
        """Charges ~91 days apart are quarterly, and prorated to a monthly cost."""
        for n in range(4):
            _add_charge(db_session, "CLOUD BACKUP", -300.0, _days_ago(n * 91))
        db_session.commit()

        result = RecurringService(db_session).get_recurring(
            today=pd.Timestamp.today().normalize()
        )
        item = result["items"][0]
        assert item["cadence"] == "quarterly"
        assert item["period_days"] == 91
        assert item["occurrences"] == 4
        assert item["monthly_equivalent"] == round(300.0 * 30 / 91, 2)
        assert item["next_expected_date"] == _days_ago(-91)

    def test_detects_annual_subscription(self, db_session):
        """Charges a year apart are annual, and count as a twelfth of a month each.

        ``new`` is relative to the cadence — three periods of an annual
        charge is three years — so a two-year-old annual renewal is still
        reported as new rather than active.
        """
        for n in range(3):
            _add_charge(db_session, "DOMAIN RENEWAL", -120.0, _days_ago(n * 365))
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=pd.Timestamp.today().normalize()
        )["items"][0]
        assert item["cadence"] == "annual"
        assert item["period_days"] == 365
        assert item["monthly_equivalent"] == round(120.0 * 30 / 365, 2)
        assert item["status"] == "new"
        assert item["next_expected_date"] == _days_ago(-365)

    def test_flags_ended_subscription_and_drops_it_from_the_total(self, db_session):
        """A monthly charge overdue by more than 1.5 periods is ``ended``.

        An ended subscription is still reported (the user may want to know it
        stopped) but must not inflate the committed monthly spend.
        """
        for n in range(6, 2, -1):
            _add_charge(db_session, "OLD MAGAZINE", -25.0, _months_ago(n))
        db_session.commit()

        result = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )
        item = result["items"][0]
        assert item["status"] == "ended"
        assert item["cadence"] == "monthly"
        assert result["total_monthly"] == 0.0

    def test_same_merchant_on_two_accounts_is_one_item(self, db_session):
        """Grouping is by merchant, not by card: both cards' charges net per day.

        The same subscription billed to two cards on the same day is one
        commitment costing the sum of the two charges; splitting it per
        account would report two half-price subscriptions instead.
        """
        for n in range(5):
            date = _months_ago(n)
            _add_charge(db_session, "NEWS DAILY", -20.0, date, account_name="card-1")
            _add_charge(db_session, "NEWS DAILY", -30.0, date, account_name="card-2")
        db_session.commit()

        result = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["amount"] == 50.0
        assert item["occurrences"] == 5
        assert item["cadence"] == "monthly"

    def test_ignores_variable_amount_merchant(self, db_session):
        """A merchant billed monthly but with wildly varying amounts (a grocery
        store, not a subscription) is rejected by the amount-stability gate."""
        amounts = [-50.0, -400.0, -80.0, -350.0, -120.0, -300.0]
        for n, amt in enumerate(amounts):
            _add_charge(db_session, "MEGA MARKET", amt, _months_ago(n), category="Food")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_ignores_irregular_cadence_merchant(self, db_session):
        """A merchant with a stable amount but irregular gaps (whose median
        still lands near a cadence) is rejected by the interval-regularity gate."""
        base = pd.Timestamp.today().normalize() - pd.DateOffset(months=8)
        # Gaps of 5, 55, 5, 55 days → median 30 (looks monthly) but very spread.
        for off in [0, 5, 60, 65, 120]:
            d = (base + pd.Timedelta(days=off)).strftime("%Y-%m-%d")
            _add_charge(db_session, "CORNER SHOP", -100.0, d, category="Food")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_same_day_refund_nets_the_charge(self, db_session):
        """A same-day partial refund reduces the detected charge magnitude."""
        for n in range(5):
            _add_charge(db_session, "NETFLIX.COM", -50.0, _months_ago(n))
        # Latest month also gets a same-day, same-merchant +15 refund → nets to -35.
        _add_charge(db_session, "NETFLIX.COM", 15.0, _months_ago(0))
        db_session.commit()

        item = RecurringService(db_session).get_recurring()["items"][0]
        assert item["last_amount"] == 35.0  # 50 charge − 15 same-day refund

    def test_fully_refunded_day_drops_occurrence(self, db_session):
        """A fully-refunded charge day is not counted as a recurring hit."""
        for n in range(3):
            _add_charge(db_session, "GYM CLUB", -30.0, _months_ago(n))
        # Fully refund the middle month on the same day, same merchant → nets to 0.
        _add_charge(db_session, "GYM CLUB", 30.0, _months_ago(1))
        db_session.commit()

        # Only 2 net-charge days remain → below the 3-occurrence threshold.
        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_excludes_project_budget_categories(self, db_session):
        """Transactions in a project-budget category are not treated as recurring."""
        from backend.constants.budget import PERIOD_PROJECT
        from backend.models.budget import BudgetRule

        db_session.add(
            BudgetRule(
                name="Home Renovation",
                category="Home Renovation",
                amount=50000,
                period_type=PERIOD_PROJECT,
            )
        )
        for n in range(4):
            _add_charge(db_session, "PAINTER", -2500.0, _months_ago(n), category="Home Renovation")
        db_session.commit()

        labels = [i["label"] for i in RecurringService(db_session).get_recurring()["items"]]
        assert "PAINTER" not in labels

    def test_excludes_non_expense_categories(self, db_session):
        """Recurring salary/income-style rows are never treated as subscriptions."""
        for n in range(5):
            _add_charge(db_session, "MONTHLY SALARY", -100.0, _months_ago(n), category="Salary")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []
