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

    def test_excludes_non_expense_categories(self, db_session):
        """Recurring salary/income-style rows are never treated as subscriptions."""
        for n in range(5):
            _add_charge(db_session, "MONTHLY SALARY", -100.0, _months_ago(n), category="Salary")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []
