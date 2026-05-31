"""Tests for RecurringService subscription detection."""

import pandas as pd

from backend.constants.tables import Tables
from backend.models.transaction import CreditCardTransaction
from backend.services.recurring_service import RecurringService


def _add_charge(db_session, description, amount, date, category="Streaming"):
    """Insert one itemized credit-card charge."""
    db_session.add(
        CreditCardTransaction(
            id=f"{description}-{date}",
            date=date,
            provider="visa",
            account_name="card-1",
            description=description,
            amount=amount,
            category=category,
            source=Tables.CREDIT_CARD.value,
        )
    )


def _months_ago(n: int, day: int = 10) -> str:
    """Return a YYYY-MM-DD string n months before today, on a fixed day."""
    d = (pd.Timestamp.today().normalize() - pd.DateOffset(months=n)).replace(day=day)
    return d.strftime("%Y-%m-%d")


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
        for n in range(4, 1, -1):  # older months at 30
            _add_charge(db_session, "GYM CLUB", -30.0, _months_ago(n))
        _add_charge(db_session, "GYM CLUB", -45.0, _months_ago(0))  # latest hiked
        db_session.commit()

        item = RecurringService(db_session).get_recurring()["items"][0]
        assert item["status"] == "price_changed"
        assert item["price_change"] > 0

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
        from backend.models.budget import BudgetRule

        db_session.add(
            BudgetRule(name="Home Renovation", category="Home Renovation", amount=50000)
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
