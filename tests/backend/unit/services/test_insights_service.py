"""Tests for InsightsService insight-card generation."""

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_YEARLY,
)
from backend.constants.tables import Tables
from backend.models.budget import BudgetRule
from backend.models.transaction import CreditCardTransaction
from backend.services.insights_service import InsightsService
from backend.services.recurring_service import RecurringService


def _add(db_session, description, amount, date, category="Food"):
    """Insert one itemized credit-card charge, and hand it back.

    The returned row carries the ``unique_id`` a large-charge insight keys on,
    once the caller has committed.
    """
    txn = CreditCardTransaction(
        id=f"{description}-{date}-{amount}",
        date=date,
        provider="visa",
        account_name="card-1",
        description=description,
        amount=amount,
        category=category,
        source=Tables.CREDIT_CARD.value,
    )
    db_session.add(txn)
    return txn


def _this_month() -> str:
    """The running month as the insight keys spell it."""
    return pd.Timestamp.today().strftime("%Y-%m")


def _months_ago(n: int, day: int = 10) -> str:
    d = (pd.Timestamp.today().normalize() - pd.DateOffset(months=n)).replace(day=day)
    return d.strftime("%Y-%m-%d")


def _project_rule(db_session, category, amount=50000.0):
    """Give ``category`` a project budget — spending there is planned, not news."""
    db_session.add(
        BudgetRule(
            name=category,
            amount=amount,
            category=category,
            tags=ALL_TAGS,
            period_type=PERIOD_PROJECT,
        )
    )


def _yearly_rule(db_session, category, amount=12000.0):
    """Give ``category`` a yearly envelope for the running year."""
    db_session.add(
        BudgetRule(
            name=category,
            amount=amount,
            category=category,
            tags=ALL_TAGS,
            year=pd.Timestamp.today().year,
            period_type=PERIOD_YEARLY,
        )
    )


def _monthly_rule(db_session, category, amount):
    """Give ``category`` a monthly budget for the running month."""
    today = pd.Timestamp.today()
    db_session.add(
        BudgetRule(
            name=category,
            amount=amount,
            category=category,
            tags=ALL_TAGS,
            year=today.year,
            month=today.month,
            period_type=PERIOD_MONTHLY,
        )
    )


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

    def test_new_recurring_surfaced_as_insight_once_confirmed(self, db_session):
        """A newly started subscription asks to be reviewed, then reports itself."""
        for n in range(3):
            _add(db_session, "DISNEY PLUS", -30.0, _months_ago(n), category="Streaming")
        db_session.commit()

        codes = {i["code"] for i in InsightsService(db_session).get_insights()}
        assert codes & {"recurringToReview"}
        assert "newRecurring" not in codes

        recurring = RecurringService(db_session)
        recurring.set_decision(
            recurring.get_recurring()["items"][0]["normalized"], "confirmed"
        )

        codes = {i["code"] for i in InsightsService(db_session).get_insights()}
        assert "newRecurring" in codes
        assert "recurringToReview" not in codes

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

    def test_one_blowout_charge_produces_one_card_not_two(self, db_session):
        """The charge that blew up a category is the news the spike already gave."""
        for n in range(1, 4):
            _add(db_session, f"GROCER {n}", -300.0, _months_ago(n), category="Food")
        _add(db_session, "CATERING", -5000.0, _months_ago(0), category="Food")
        db_session.commit()

        codes = [i["code"] for i in InsightsService(db_session).get_insights()]
        assert "categorySpike" in codes
        assert "largeTransaction" not in codes


class TestPlannedSpendIsNotNews:
    """Spending the budget already accounts for never becomes a spike."""

    @staticmethod
    def _seed_spike(db_session, category):
        """Three quiet months in ``category``, then a month five times as big."""
        for n in range(1, 4):
            _add(db_session, f"PAY {n}", -300.0, _months_ago(n), category=category)
        _add(db_session, "PAY NOW", -1500.0, _months_ago(0), category=category)

    def test_project_category_spike_is_suppressed(self, db_session):
        """A project budget is a deliberate lump — outspending its own history is the point."""
        self._seed_spike(db_session, "Home Renovation")
        _project_rule(db_session, "Home Renovation")
        db_session.commit()

        assert InsightsService(db_session)._category_spike_insights() == []

    def test_project_category_still_spikes_without_the_project_rule(self, db_session):
        """The suppression is the budget rule's doing, not the category's name."""
        self._seed_spike(db_session, "Home Renovation")
        db_session.commit()

        result = InsightsService(db_session)._category_spike_insights()
        assert [i["data"]["category"] for i in result] == ["Home Renovation"]

    def test_yearly_envelope_spike_is_suppressed(self, db_session):
        """A yearly envelope is lumpy by design — one heavy month proves nothing."""
        self._seed_spike(db_session, "Insurance")
        _yearly_rule(db_session, "Insurance")
        db_session.commit()

        assert InsightsService(db_session)._category_spike_insights() == []

    def test_spend_inside_its_monthly_budget_is_not_a_spike(self, db_session):
        """Above trend but within plan is the budget page's business, not an alert."""
        self._seed_spike(db_session, "Food")
        _monthly_rule(db_session, "Food", 2000.0)
        db_session.commit()

        assert InsightsService(db_session)._category_spike_insights() == []

    def test_spend_past_its_monthly_budget_still_spikes(self, db_session):
        """Once the plan is breached the spike is real news again."""
        self._seed_spike(db_session, "Food")
        _monthly_rule(db_session, "Food", 1000.0)
        db_session.commit()

        result = InsightsService(db_session)._category_spike_insights()
        assert [i["data"]["category"] for i in result] == ["Food"]


class TestCategorySpikeNeedsATrend:
    """A category must have a normal before it can deviate from one."""

    @staticmethod
    def _seed_three_prior_months(db_session):
        """Populate the baseline window so month coverage is never the blocker."""
        for n in range(1, 4):
            _add(db_session, f"GROCER {n}", -300.0, _months_ago(n), category="Food")

    def test_category_seen_in_only_one_baseline_month_is_ignored(self, db_session):
        """One prior sighting is an occasion, not a trend to spike above."""
        self._seed_three_prior_months(db_session)
        _add(db_session, "GIFT", -300.0, _months_ago(1), category="Gifts")
        _add(db_session, "GIFT NOW", -2000.0, _months_ago(0), category="Gifts")
        db_session.commit()

        result = InsightsService(db_session)._category_spike_insights()
        assert [i["data"]["category"] for i in result] == []

    def test_baseline_is_the_median_so_one_odd_month_cannot_set_the_normal(self, db_session):
        """A single huge baseline month must not redefine "usual" for the rest."""
        _add(db_session, "GROCER 1", -300.0, _months_ago(1), category="Food")
        _add(db_session, "GROCER 2", -300.0, _months_ago(2), category="Food")
        _add(db_session, "GROCER 3", -6000.0, _months_ago(3), category="Food")
        _add(db_session, "GROCER NOW", -1500.0, _months_ago(0), category="Food")
        db_session.commit()

        result = InsightsService(db_session)._category_spike_insights()
        # Median baseline is 300 (not the 2,200 mean), so 1,500 is a spike.
        assert [i["data"]["percent"] for i in result] == [400]

    def test_floor_scales_with_the_household(self, db_session, monkeypatch):
        """A delta that matters at 3,000/month is rounding at 50,000/month."""
        self._seed_three_prior_months(db_session)
        _add(db_session, "GROCER NOW", -1500.0, _months_ago(0), category="Food")
        db_session.commit()

        service = InsightsService(db_session)
        monkeypatch.setattr(service, "_spending_baseline", lambda: 50_000.0)
        assert service._category_spike_insights() == []


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
            {
                "code": "overspendPace",
                "key": f"overspendPace:{_this_month()}",
                "severity": "warning",
                "data": {"amount": 2345.68},
            }
        ]

    def test_gap_inside_the_forecast_error_bars_is_not_a_warning(self, db_session, monkeypatch):
        """A gap under 5% of expected income is noise in the projection itself."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=10400.0, projected_net=-400.0
        )
        assert service._pace_insight() == []

    def test_gap_a_running_project_accounts_for_is_not_a_warning(self, db_session, monkeypatch):
        """Overspending because a planned project is drawing is the plan, not a surprise."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=12345.678, projected_net=-2345.678
        )
        monkeypatch.setattr(service, "_project_spend_this_month", lambda: 3000.0)
        assert service._pace_insight() == []

    def test_positive_projection_is_on_track(self, db_session, monkeypatch):
        """A positive projected net is a positive onTrack card."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=8000.0, projected_net=2000.0
        )
        assert service._pace_insight() == [
            {
                "code": "onTrack",
                "key": f"onTrack:{_this_month()}",
                "severity": "positive",
                "data": {"amount": 2000.0},
            }
        ]

    def test_barely_positive_projection_is_not_worth_a_card(self, db_session, monkeypatch):
        """Saving 1% of income is within the noise, not a win to announce."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=9900.0, projected_net=100.0
        )
        assert service._pace_insight() == []

    def test_break_even_yields_nothing(self, db_session, monkeypatch):
        """Exactly break-even is neither a warning nor a win."""
        service = self._service_with_forecast(
            db_session, monkeypatch, expected_income=10000.0, expected_expenses=10000.0, projected_net=0.0
        )
        assert service._pace_insight() == []


class TestRecurringInsights:
    """Recurring-item statuses map to newRecurring / priceIncrease / priceDecrease."""

    @staticmethod
    def _service_with_items(db_session, monkeypatch, items, pending_count=0):
        service = InsightsService(db_session)
        summary = {
            "items": items,
            "pending_count": pending_count,
            "pending_monthly": 0.0,
        }
        monkeypatch.setattr(service.recurring, "get_recurring", lambda: summary)
        return service

    @staticmethod
    def _item(status, price_change=0.0, label="Gym", confirmation="confirmed"):
        return {
            "label": label,
            "amount": 120.0,
            "last_amount": 120.0 + price_change,
            "cadence": "monthly",
            "status": status,
            "price_change": price_change,
            "confirmation": confirmation,
        }

    def test_price_increase_is_a_warning_and_decrease_is_info(self, db_session, monkeypatch):
        """The sign of the change picks the code and severity; delta is absolute."""
        service = self._service_with_items(
            db_session,
            monkeypatch,
            [self._item("price_changed", 40.0, "Gym"), self._item("price_changed", -25.0, "Netflix")],
        )

        result = service._recurring_insights()

        assert result == [
            {
                "code": "priceIncrease",
                "key": "priceIncrease:Gym:160.0",
                "severity": "warning",
                "data": {"label": "Gym", "delta": 40.0, "amount": 160.0},
            },
            {
                "code": "priceDecrease",
                "key": "priceDecrease:Netflix:95.0",
                "severity": "info",
                "data": {"label": "Netflix", "delta": 25.0, "amount": 95.0},
            },
        ]

    def test_a_few_shekels_of_drift_is_not_a_price_change_worth_reading(self, db_session, monkeypatch):
        """Detection reports any move past its tolerance; a card needs a real one."""
        service = self._service_with_items(
            db_session, monkeypatch, [self._item("price_changed", 8.0, "Gym")]
        )
        assert service._recurring_insights() == []

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

    def test_unconfirmed_items_never_become_cards(self, db_session, monkeypatch):
        """A candidate nobody has ruled on is a question, not a finding."""
        service = self._service_with_items(
            db_session,
            monkeypatch,
            [self._item("new", confirmation="pending")],
        )
        assert service._recurring_insights() == []

    def test_pending_candidates_get_one_review_card(self, db_session, monkeypatch):
        """Waiting candidates produce a single nudge to review them."""
        service = self._service_with_items(
            db_session,
            monkeypatch,
            [self._item("new", confirmation="pending") for _ in range(4)],
            pending_count=4,
        )
        result = service._recurring_insights()
        assert [card["code"] for card in result] == ["recurringToReview"]
        assert result[0]["data"]["count"] == 4


class TestLargeTransactionInsight:
    """A single outsized charge this month is flagged when nothing explains it."""

    def _seed_baseline(self, db_session, n=8, amount=-50.0):
        for i in range(n):
            _add(db_session, f"coffee {i}", amount, _months_ago(1 + i % 3, day=5 + i))

    def test_outlier_this_month_is_flagged_with_its_description(self, db_session):
        """A charge ≥ 4× the median and ≥ 1,000 becomes a largeTransaction card."""
        self._seed_baseline(db_session)
        laptop = _add(
            db_session, "New Laptop", -4200.0, _months_ago(0, day=3), category="Electronics"
        )
        db_session.commit()

        result = InsightsService(db_session)._large_transaction_insight()

        assert result == [
            {
                "code": "largeTransaction",
                "key": f"largeTransaction:{Tables.CREDIT_CARD.value}:{laptop.unique_id}",
                "severity": "info",
                "data": {
                    "label": "New Laptop",
                    "amount": 4200.0,
                    "category": "Electronics",
                },
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

    def test_a_charge_the_category_has_seen_before_is_not_unusual(self, db_session):
        """"Large" means large for this category, not large in the abstract."""
        self._seed_baseline(db_session)
        _add(db_session, "Old Laptop", -4200.0, _months_ago(2, day=3), category="Electronics")
        _add(db_session, "New Laptop", -4000.0, _months_ago(0, day=3), category="Electronics")
        db_session.commit()

        assert InsightsService(db_session)._large_transaction_insight() == []

    def test_project_charges_are_never_unusual(self, db_session):
        """The painter's invoice is what the renovation budget was opened for."""
        self._seed_baseline(db_session)
        _add(db_session, "PAINTER", -9000.0, _months_ago(0, day=3), category="Home Renovation")
        _project_rule(db_session, "Home Renovation")
        db_session.commit()

        assert InsightsService(db_session)._large_transaction_insight() == []

    def test_a_skipped_charge_does_not_hide_a_real_one_below_it(self, db_session):
        """The scan continues past an explained charge to the next candidate."""
        self._seed_baseline(db_session)
        _add(db_session, "PAINTER", -9000.0, _months_ago(0, day=3), category="Home Renovation")
        _project_rule(db_session, "Home Renovation")
        _add(db_session, "New Laptop", -4200.0, _months_ago(0, day=4), category="Electronics")
        db_session.commit()

        result = InsightsService(db_session)._large_transaction_insight()
        assert [i["data"]["label"] for i in result] == ["New Laptop"]

    def test_a_confirmed_recurring_bill_is_not_a_surprise(self, db_session):
        """Rent is large every month — that is the opposite of news."""
        self._seed_baseline(db_session)
        for n in range(1, 6):
            _add(db_session, "MORTGAGE", -5000.0, _months_ago(n, day=2), category="Housing")
        _add(db_session, "MORTGAGE", -6000.0, _months_ago(0, day=2), category="Housing")
        db_session.commit()

        service = InsightsService(db_session)
        assert [i["data"]["label"] for i in service._large_transaction_insight()] == ["MORTGAGE"]

        recurring = RecurringService(db_session)
        mortgage = next(
            i for i in recurring.get_recurring()["items"] if "mortgage" in i["normalized"]
        )
        recurring.set_decision(mortgage["normalized"], "confirmed")

        assert InsightsService(db_session)._large_transaction_insight() == []


class TestInsightOrderingAndCap:
    """The combined list is severity-sorted, size-ranked and capped."""

    def test_warnings_first_then_info_then_positive_capped(self, db_session, monkeypatch):
        """Cards are ordered warning → info → positive and truncated to the cap."""
        service = InsightsService(db_session)
        monkeypatch.setattr(
            service, "_pace_insight", lambda: [{"code": "onTrack", "severity": "positive", "data": {"amount": 5.0}}]
        )
        monkeypatch.setattr(
            service,
            "_category_spike_insights",
            lambda: [
                {"code": "categorySpike", "severity": "warning", "data": {"category": f"c{i}", "amount": 100.0 * i}}
                for i in range(2)
            ],
        )
        monkeypatch.setattr(
            service,
            "_recurring_insights",
            lambda: [{"code": "newRecurring", "severity": "info", "data": {"amount": 10.0 * i}} for i in range(3)],
        )
        monkeypatch.setattr(
            service,
            "_large_transaction_insight",
            lambda: [{"code": "largeTransaction", "severity": "info", "data": {"amount": 9000.0}}],
        )

        result = service.get_insights()

        assert len(result) == service._MAX_INSIGHTS
        severities = [r["severity"] for r in result]
        assert severities == sorted(severities, key={"warning": 0, "info": 1, "positive": 2}.get)
        assert severities[:2] == ["warning", "warning"]
        assert "positive" not in severities
        # Within a band the biggest sum of money leads.
        assert result[0]["data"]["amount"] == 100.0
        assert result[2]["code"] == "largeTransaction"


class TestDismissal:
    """A dismissed card stays gone until the thing it described changes."""

    @staticmethod
    def _seed_spike(db_session, category="Food"):
        """Three quiet months, then a month five times as big."""
        for n in range(1, 4):
            _add(db_session, f"GROCER {n}", -300.0, _months_ago(n), category=category)
        _add(db_session, "GROCER NOW", -1500.0, _months_ago(0), category=category)

    def test_dismissed_card_disappears_and_comes_back_on_restore(self, db_session):
        """Dismiss hides exactly one card; restore undoes it."""
        self._seed_spike(db_session)
        db_session.commit()

        key = InsightsService(db_session)._category_spike_insights()[0]["key"]

        InsightsService(db_session).dismiss(key)
        assert InsightsService(db_session)._category_spike_insights() == []

        InsightsService(db_session).restore(key)
        assert [i["key"] for i in InsightsService(db_session)._category_spike_insights()] == [key]

    def test_dismissing_is_idempotent(self, db_session):
        """Two clicks on the same X are one dismissal, not a duplicate row."""
        self._seed_spike(db_session)
        db_session.commit()
        key = InsightsService(db_session)._category_spike_insights()[0]["key"]

        InsightsService(db_session).dismiss(key)
        InsightsService(db_session).dismiss(key)

        assert InsightsService(db_session).dismissals.get_keys() == {key}

    def test_a_dismissal_frees_the_slot_it_occupied(self, db_session):
        """Waving away the top spike promotes the runner-up, not a shorter strip."""
        for category in ("Food", "Transportation", "Shopping"):
            for n in range(1, 4):
                _add(db_session, f"{category} {n}", -300.0, _months_ago(n), category=category)
        _add(db_session, "FOOD NOW", -3000.0, _months_ago(0), category="Food")
        _add(db_session, "TRANSPORT NOW", -2000.0, _months_ago(0), category="Transportation")
        _add(db_session, "SHOPPING NOW", -1500.0, _months_ago(0), category="Shopping")
        db_session.commit()

        before = [i["data"]["category"] for i in InsightsService(db_session)._category_spike_insights()]
        assert before == ["Food", "Transportation"]

        InsightsService(db_session).dismiss(f"categorySpike:Food:{_this_month()}")

        after = [i["data"]["category"] for i in InsightsService(db_session)._category_spike_insights()]
        assert after == ["Transportation", "Shopping"]

    def test_next_month_is_a_new_card(self, db_session):
        """The key carries the month, so a dismissal cannot silence the next one."""
        self._seed_spike(db_session)
        db_session.commit()

        service = InsightsService(db_session)
        key = service._category_spike_insights()[0]["key"]
        assert key.endswith(_this_month())

    def test_a_dismissed_large_charge_lets_the_next_one_through(self, db_session):
        """The scan continues past a dismissed charge to the next candidate."""
        for i in range(8):
            _add(db_session, f"coffee {i}", -50.0, _months_ago(1 + i % 3, day=5 + i))
        _add(db_session, "New Laptop", -4200.0, _months_ago(0, day=3), category="Electronics")
        _add(db_session, "New Sofa", -3000.0, _months_ago(0, day=4), category="Furniture")
        db_session.commit()

        first = InsightsService(db_session)._large_transaction_insight()[0]
        assert first["data"]["label"] == "New Laptop"

        InsightsService(db_session).dismiss(first["key"])

        second = InsightsService(db_session)._large_transaction_insight()
        assert [i["data"]["label"] for i in second] == ["New Sofa"]

    def test_dismissing_one_card_leaves_the_others(self, db_session, monkeypatch):
        """Only the card whose key was dismissed goes away."""
        service = InsightsService(db_session)
        monkeypatch.setattr(
            service.analysis,
            "get_cash_flow_forecast",
            lambda: {
                "expected_income": 10000.0,
                "expected_expenses": 8000.0,
                "projected_net": 2000.0,
                "avg_monthly_expenses": 8000.0,
            },
        )
        assert [i["code"] for i in service._pace_insight()] == ["onTrack"]

        InsightsService(db_session).dismiss(f"onTrack:{_this_month()}")

        fresh = InsightsService(db_session)
        monkeypatch.setattr(
            fresh.analysis,
            "get_cash_flow_forecast",
            lambda: {
                "expected_income": 10000.0,
                "expected_expenses": 8000.0,
                "projected_net": 2000.0,
                "avg_monthly_expenses": 8000.0,
            },
        )
        assert fresh._pace_insight() == []
