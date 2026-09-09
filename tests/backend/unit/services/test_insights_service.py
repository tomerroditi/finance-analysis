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


class TestPaceInsight:
    """Branches of the month-pace insight, driven by a stubbed forecast."""

    @staticmethod
    def _service_with_forecast(db_session, monkeypatch, **forecast):
        service = InsightsService(db_session)
        monkeypatch.setattr(service.analysis, "get_cash_flow_forecast", lambda: forecast)
        return service

    def test_no_income_baseline_yields_nothing(self, db_session, monkeypatch):
        """Without expected income there is no pace to judge."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=0.0, expected_expenses=500.0, projected_net=-500.0
        )
        assert service._pace_insight() == []

    def test_overspend_pace_is_a_warning_with_the_gap(self, db_session, monkeypatch):
        """Expenses above income produce an overspendPace warning sized to the gap."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=12345.678, projected_net=-2345.678
        )
        assert service._pace_insight() == [
            {"code": "overspendPace", "severity": "warning", "data": {"amount": 2345.68}}
        ]

    def test_positive_projection_is_on_track(self, db_session, monkeypatch):
        """A positive projected net is a positive onTrack card."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=8000.0, projected_net=2000.0
        )
        assert service._pace_insight() == [
            {"code": "onTrack", "severity": "positive", "data": {"amount": 2000.0}}
        ]

    def test_break_even_yields_nothing(self, db_session, monkeypatch):
        """Exactly break-even is neither a warning nor a win."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=10000.0, projected_net=0.0
        )
        assert service._pace_insight() == []


class TestRecurringInsights:
    """Recurring-item statuses map to newRecurring / priceIncrease / priceDecrease."""

    @staticmethod
    def _service_with_items(db_session, monkeypatch, items):
        service = InsightsService(db_session)
        monkeypatch.setattr(service.recurring, "get_recurring", lambda: {"items": items})
        return service

    @staticmethod
    def _item(status, price_change=0.0, label="Gym"):
        return {
            "label": label,
            "amount": 120.0,
            "last_amount": 120.0 + price_change,
            "cadence": "monthly",
            "status": status,
            "price_change": price_change,
        }

    def test_price_increase_is_a_warning_and_decrease_is_info(self, db_session, monkeypatch):
        """The sign of the change picks the code and severity; delta is absolute."""
        service = self._service_with_items(
            db_session,
            monkeypatch,
            [self._item("price_changed", 15.0, "Gym"), self._item("price_changed", -5.0, "Netflix")],
        )

        result = service._recurring_insights()

        assert result == [
            {
                "code": "priceIncrease",
                "severity": "warning",
                "data": {"label": "Gym", "delta": 15.0, "amount": 135.0},
            },
            {
                "code": "priceDecrease",
                "severity": "info",
                "data": {"label": "Netflix", "delta": 5.0, "amount": 115.0},
            },
        ]

    def test_active_and_ended_items_are_ignored(self, db_session, monkeypatch):
        """Only new and price-changed subscriptions become cards."""
        service = self._service_with_items(
            db_session, monkeypatch, [self._item("active"), self._item("ended")]
        )
        assert service._recurring_insights() == []

    def test_at_most_three_recurring_cards(self, db_session, monkeypatch):
        """A burst of new subscriptions is capped at three cards."""
        service = self._service_with_items(
            db_session, monkeypatch, [self._item("new", label=f"Sub {i}") for i in range(6)]
        )
        result = service._recurring_insights()
        assert len(result) == 3
        assert all(r["code"] == "newRecurring" for r in result)


class TestLargeTransactionInsight:
    """A single outsized charge this month is flagged against the median charge."""

    def _seed_baseline(self, db_session, n=8, amount=-50.0):
        for i in range(n):
            _add(db_session, f"coffee {i}", amount, _months_ago(1 + i % 3, day=5 + i))

    def test_outlier_this_month_is_flagged_with_its_description(self, db_session):
        """A charge ≥ 4× the median and ≥ 1,000 becomes a largeTransaction card."""
        self._seed_baseline(db_session)
        _add(db_session, "New Laptop", -4200.0, _months_ago(0, day=3), category="Electronics")
        db_session.commit()

        result = InsightsService(db_session)._large_transaction_insight()

        assert result == [
            {
                "code": "largeTransaction",
                "severity": "info",
                "data": {"label": "New Laptop", "amount": 4200.0},
            }
        ]

    def test_big_but_not_big_enough_is_ignored(self, db_session):
        """Below the absolute floor nothing is flagged even if it dwarfs the median."""
        self._seed_baseline(db_session, amount=-20.0)
        _add(db_session, "Shoes", -600.0, _months_ago(0, day=3))
        db_session.commit()

        assert InsightsService(db_session)._large_transaction_insight() == []

    def test_outlier_in_a_previous_month_is_ignored(self, db_session):
        """Only the running month is inspected."""
        self._seed_baseline(db_session)
        _add(db_session, "Old Laptop", -4200.0, _months_ago(2, day=3))
        db_session.commit()

        assert InsightsService(db_session)._large_transaction_insight() == []

    def test_income_and_non_expense_categories_are_ignored(self, db_session):
        """Salary-sized inflows and investment transfers never count as large expenses."""
        self._seed_baseline(db_session)
        _add(db_session, "Salary", 25000.0, _months_ago(0, day=1), category="Salary")
        _add(db_session, "Broker transfer", -9000.0, _months_ago(0, day=2), category="Investments")
        db_session.commit()

        assert InsightsService(db_session)._large_transaction_insight() == []


class TestInsightOrderingAndCap:
    """The combined list is severity-sorted and capped."""

    def test_warnings_first_then_info_then_positive_capped_at_eight(self, db_session, monkeypatch):
        """Cards are ordered warning → info → positive and truncated to eight."""
        service = InsightsService(db_session)
        monkeypatch.setattr(
            service, "_pace_insight", lambda: [{"code": "onTrack", "severity": "positive", "data": {}}]
        )
        monkeypatch.setattr(
            service,
            "_category_spike_insights",
            lambda: [{"code": "categorySpike", "severity": "warning", "data": {"i": i}} for i in range(2)],
        )
        monkeypatch.setattr(
            service,
            "_recurring_insights",
            lambda: [{"code": "newRecurring", "severity": "info", "data": {"i": i}} for i in range(3)],
        )
        monkeypatch.setattr(
            service,
            "_large_transaction_insight",
            lambda: [{"code": "largeTransaction", "severity": "info", "data": {"i": i}} for i in range(4)],
        )

        result = service.get_insights()

        assert len(result) == 8
        severities = [r["severity"] for r in result]
        assert severities == sorted(severities, key={"warning": 0, "info": 1, "positive": 2}.get)
        assert severities[:2] == ["warning", "warning"]
        assert "positive" not in severities
