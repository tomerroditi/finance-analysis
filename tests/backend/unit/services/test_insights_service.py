"""Tests for InsightsService insight-card generation."""

import pandas as pd

from backend.constants.tables import Tables
from backend.models.transaction import CreditCardTransaction
from backend.services.insights_service import InsightsService


def _add(db_session, description, amount, date, category="Food"):
    """Insert one itemized credit-card charge."""
    db_session.add(
        CreditCardTransaction(
            id=f"{description}-{date}-{amount}",
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
    d = (pd.Timestamp.today().normalize() - pd.DateOffset(months=n)).replace(day=day)
    return d.strftime("%Y-%m-%d")


class TestInsights:
    """Tests for InsightsService.get_insights."""

    def test_empty_db_no_crash(self, db_session):
        """Empty DB returns an empty list without raising."""
        assert InsightsService(db_session).get_insights() == []

    def test_insights_are_well_shaped(self, db_session):
        """Each insight carries a code, severity and data payload."""
        for n in range(5):
            _add(db_session, "NETFLIX 1", -45.0, _months_ago(n), category="Streaming")
        db_session.commit()

        for insight in InsightsService(db_session).get_insights():
            assert "code" in insight
            assert insight["severity"] in {"positive", "info", "warning"}
            assert isinstance(insight["data"], dict)

    def test_new_recurring_surfaced_as_insight(self, db_session):
        """A newly started subscription produces a newRecurring insight."""
        for n in range(3):
            _add(db_session, "DISNEY PLUS", -30.0, _months_ago(n), category="Streaming")
        db_session.commit()

        codes = {i["code"] for i in InsightsService(db_session).get_insights()}
        assert "newRecurring" in codes

    def test_category_spike_detected(self, db_session):
        """A category spending far above its trend produces a categorySpike."""
        # Three prior months of modest Food spend.
        for n in range(1, 4):
            _add(db_session, f"GROCER {n}", -300.0, _months_ago(n), category="Food")
        # Current month: a big jump.
        _add(db_session, "GROCER NOW", -1500.0, _months_ago(0), category="Food")
        db_session.commit()

        codes = {i["code"] for i in InsightsService(db_session).get_insights()}
        assert "categorySpike" in codes
