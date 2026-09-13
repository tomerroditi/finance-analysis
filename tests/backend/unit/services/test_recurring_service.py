"""Tests for RecurringService subscription detection."""

import pandas as pd
import pytest

from backend.constants.tables import Tables
from backend.errors import EntityNotFoundException, ValidationException
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
        assert result == {
            "items": [],
            "total_monthly": 0.0,
            "pending_monthly": 0.0,
            "pending_count": 0,
            "confirmed_count": 0,
            "dismissed_count": 0,
        }

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
        # Undecided candidates are not in the confirmed total.
        assert item["confirmation"] == "pending"
        assert result["total_monthly"] == 0.0
        assert result["pending_monthly"] == 45.0
        assert result["pending_count"] == 1

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


class TestRecurringConfirmation:
    """Tests for the confirm / dismiss gate in front of detection."""

    @staticmethod
    def _seed_netflix(db_session):
        """Seed a clean five-month monthly subscription and return its key."""
        for n in range(5):
            _add_charge(db_session, "NETFLIX.COM 1234", -45.0, _months_ago(n))
        db_session.commit()
        return RecurringService(db_session).get_recurring()["items"][0]["normalized"]

    def test_new_candidate_is_pending(self, db_session):
        """A freshly detected charge is reported as pending, not confirmed."""
        self._seed_netflix(db_session)

        result = RecurringService(db_session).get_recurring()
        assert result["items"][0]["confirmation"] == "pending"
        assert result["confirmed_count"] == 0
        assert result["pending_count"] == 1

    def test_confirming_moves_it_into_the_total(self, db_session):
        """Confirming flips the verdict and adds the item to the monthly total."""
        norm = self._seed_netflix(db_session)
        service = RecurringService(db_session)

        service.set_decision(norm, "confirmed")

        result = RecurringService(db_session).get_recurring()
        assert result["items"][0]["confirmation"] == "confirmed"
        assert result["total_monthly"] == 45.0
        assert result["pending_monthly"] == 0.0

    def test_confirmed_items_are_what_downstream_reads(self, db_session):
        """``get_confirmed_items`` is empty until the user confirms."""
        norm = self._seed_netflix(db_session)
        service = RecurringService(db_session)
        assert service.get_confirmed_items() == []

        service.set_decision(norm, "confirmed")
        confirmed = RecurringService(db_session).get_confirmed_items()
        assert [item["normalized"] for item in confirmed] == [norm]

    def test_dismissed_candidate_is_hidden_by_default(self, db_session):
        """A dismissed charge drops out of the list but is still counted."""
        norm = self._seed_netflix(db_session)
        RecurringService(db_session).set_decision(norm, "dismissed")

        result = RecurringService(db_session).get_recurring()
        assert result["items"] == []
        assert result["dismissed_count"] == 1

        with_dismissed = RecurringService(db_session).get_recurring(
            include_dismissed=True
        )
        assert with_dismissed["items"][0]["confirmation"] == "dismissed"

    def test_verdict_survives_new_charges(self, db_session):
        """A later charge on a confirmed merchant does not reopen the question."""
        norm = self._seed_netflix(db_session)
        RecurringService(db_session).set_decision(norm, "confirmed")

        _add_charge(db_session, "NETFLIX.COM 9981", -45.0, _days_ago(1))
        db_session.commit()

        result = RecurringService(db_session).get_recurring()
        assert result["items"][0]["confirmation"] == "confirmed"
        assert result["pending_count"] == 0

    def test_pending_undoes_a_verdict(self, db_session):
        """Setting ``pending`` puts a decided candidate back up for review."""
        norm = self._seed_netflix(db_session)
        service = RecurringService(db_session)
        service.set_decision(norm, "dismissed")
        service.set_decision(norm, "pending")

        result = RecurringService(db_session).get_recurring()
        assert result["items"][0]["confirmation"] == "pending"
        assert result["dismissed_count"] == 0

    def test_bulk_decisions_confirm_everything_at_once(self, db_session):
        """``set_decisions`` stores a whole batch — the "confirm all" path."""
        for n in range(5):
            _add_charge(db_session, "NETFLIX.COM 1234", -45.0, _months_ago(n))
            _add_charge(db_session, "SPOTIFY AB", -20.0, _months_ago(n))
        db_session.commit()

        service = RecurringService(db_session)
        keys = [item["normalized"] for item in service.get_recurring()["items"]]
        service.set_decisions(
            [{"normalized": key, "decision": "confirmed"} for key in keys]
        )

        result = RecurringService(db_session).get_recurring()
        assert result["confirmed_count"] == 2
        assert result["total_monthly"] == 65.0

    def test_unknown_key_is_rejected(self, db_session):
        """Confirming something detection never produced is a 404, not a no-op."""
        with pytest.raises(EntityNotFoundException):
            RecurringService(db_session).set_decision("no such merchant", "confirmed")

    def test_invalid_decision_is_rejected(self, db_session):
        """Only the three known verdicts are accepted."""
        norm = self._seed_netflix(db_session)
        with pytest.raises(ValidationException):
            RecurringService(db_session).set_decision(norm, "maybe")


def _from(base: str, offsets: list[int]) -> list[str]:
    """Return ``base`` shifted by each offset in days, as YYYY-MM-DD strings."""
    start = pd.Timestamp(base)
    return [(start + pd.Timedelta(days=o)).strftime("%Y-%m-%d") for o in offsets]


class TestCadenceMatching:
    """The cadence bands are tight and do not overlap."""

    def test_each_cadence_claims_its_own_period(self, db_session):
        """A gap at the centre of a band is matched to that band."""
        service = RecurringService(db_session)
        for name, days, _tolerance in service._CADENCES:
            assert service._match_cadence(days) == (name, days)

    def test_a_gap_between_two_bands_is_not_a_cadence(self, db_session):
        """38 and 45 days belong to nothing — they are not rounded to monthly.

        The old single ±35% tolerance stretched "monthly" from 19.5 to 40.5
        days, which is where most of the false positives lived.
        """
        service = RecurringService(db_session)
        assert service._match_cadence(38) is None
        assert service._match_cadence(45) is None
        assert service._match_cadence(20) is None

    def test_bimonthly_is_no_longer_swallowed_by_quarterly(self, db_session):
        """A two-month gap matches bimonthly, not quarterly."""
        assert RecurringService(db_session)._match_cadence(61) == ("bimonthly", 61)


class TestAnchorScore:
    """Charges are scored on how tightly they land on one billing day."""

    def test_a_fixed_day_of_month_scores_perfectly(self, db_session):
        """Every charge on the 12th anchors completely."""
        dates = pd.Series(pd.to_datetime(["2026-01-12", "2026-02-12", "2026-03-12"]))
        assert RecurringService(db_session)._anchor_score(dates, 30) == 1.0

    def test_the_month_wrap_is_measured_circularly(self, db_session):
        """The 1st and the 30th are two days apart, not twenty-nine."""
        dates = pd.Series(pd.to_datetime(["2026-01-30", "2026-03-01", "2026-03-31"]))
        assert RecurringService(db_session)._anchor_score(dates, 30) == 1.0

    def test_scattered_days_score_low(self, db_session):
        """Days spread across the month do not anchor."""
        dates = pd.Series(pd.to_datetime(["2026-01-03", "2026-02-14", "2026-03-27"]))
        assert RecurringService(db_session)._anchor_score(dates, 30) < 0.7

    def test_week_cadences_anchor_on_the_weekday(self, db_session):
        """A weekly charge is judged on its day of the week, not of the month."""
        dates = pd.Series(pd.to_datetime(["2026-01-05", "2026-01-12", "2026-01-19"]))
        assert RecurringService(db_session)._anchor_score(dates, 7) == 1.0


class TestFalsePositivesRejected:
    """Patterns the loosened old criteria accepted and the new ones do not."""

    def test_scattered_gaps_around_a_monthly_median_are_rejected(self, db_session):
        """Gaps of 24 and 36 days around a monthly median are not a cadence.

        The old gate measured spread with a standard deviation and allowed
        anything under 0.5, which this clears comfortably at 0.18. The measured
        threshold — every real commitment in the demo history scores at most
        0.133 — rejects it.
        """
        for date in _from("2026-01-06", [0, 30, 54, 90, 114, 150]):
            _add_charge(db_session, "CORNER BAKERY", -60.0, date, category="Food")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_a_38_day_rhythm_is_not_monthly(self, db_session):
        """A perfectly even 38-day gap matches no cadence at all."""
        for date in _from("2026-01-05", [0, 38, 76, 114, 152]):
            _add_charge(db_session, "HAIR SALON", -180.0, date)
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_a_weekly_habit_needs_more_than_a_month_of_evidence(self, db_session):
        """Four same-weekday charges are a routine, not yet a subscription."""
        for date in _from("2026-01-05", [0, 7, 14, 21]):
            _add_charge(db_session, "MONDAY COFFEE", -15.0, date, category="Food")
        db_session.commit()

        assert RecurringService(db_session).get_recurring()["items"] == []

    def test_a_variable_amount_needs_more_sightings_than_a_fixed_one(self, db_session):
        """Three evenly spaced annual charges qualify only at a steady price.

        Three points are trivially "regular" whatever they cost, so a candidate
        whose amount carries no evidence has to show the schedule more times.
        A yearly back-to-school run and a yearly hotel booking got in as
        subscriptions exactly this way.
        """
        for n, amount in enumerate([-180.0, -260.0, -210.0]):
            _add_charge(db_session, "BACK TO SCHOOL", amount, _from("2024-08-20", [n * 365])[0])
        for date in _from("2024-09-04", [0, 365, 730]):
            _add_charge(db_session, "DOMAIN RENEWAL", -120.0, date)
        db_session.commit()

        labels = [
            item["label"]
            for item in RecurringService(db_session).get_recurring(
                today=pd.Timestamp("2026-09-10")
            )["items"]
        ]
        assert labels == ["DOMAIN RENEWAL"]

    def test_a_weekly_charge_with_enough_evidence_is_kept(self, db_session):
        """The same charge seen six times clears the weekly floor.

        Guards the floor against being read as "weekly is never recurring".
        """
        for date in _from("2026-01-05", [0, 7, 14, 21, 28, 35]):
            _add_charge(db_session, "CLEANER", -200.0, date)
        db_session.commit()

        items = RecurringService(db_session).get_recurring(
            today=pd.Timestamp("2026-02-10")
        )["items"]
        assert [i["cadence"] for i in items] == ["weekly"]


class TestTruePositivesGained:
    """Real commitments the old criteria threw away."""

    def test_a_metered_utility_bill_is_detected(self, db_session):
        """A bill on the same day each month qualifies even as the amount swings.

        Electricity and water move with consumption, so they could never clear
        a fixed-price amount band. They earn their place with an exact schedule
        instead, and are reported as ``metered`` so the reviewer knows why.
        """
        amounts = [-300.0, -480.0, -250.0, -420.0, -310.0, -450.0]
        for n, amount in enumerate(amounts):
            _add_charge(
                db_session, "ELECTRIC CO", amount, _months_ago(5 - n), category="Home"
            )
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )["items"][0]
        assert item["cadence"] == "monthly"
        assert item["amount_kind"] == "metered"

    def test_a_bimonthly_bill_is_priced_per_two_months(self, db_session):
        """A 61-day bill is bimonthly, so its monthly cost is halved, not thirded.

        It used to land in the quarterly band, which understated what it costs
        per month by a third.
        """
        for date in _from("2026-01-08", [0, 61, 122, 183]):
            _add_charge(db_session, "WATER CORP", -240.0, date, category="Home")
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=pd.Timestamp("2026-07-10")
        )["items"][0]
        assert item["cadence"] == "bimonthly"
        assert item["period_days"] == 61
        assert item["monthly_equivalent"] == round(240.0 * 30 / 61, 2)

    def test_a_semiannual_charge_is_detected(self, db_session):
        """A half-yearly premium used to fall between the quarterly and annual bands."""
        for date in _from("2026-01-15", [0, 182, 364]):
            _add_charge(db_session, "CAR INSURANCE", -1800.0, date)
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=pd.Timestamp("2027-01-20")
        )["items"][0]
        assert item["cadence"] == "semiannual"
        assert item["period_days"] == 182

    def test_a_skipped_period_does_not_reject_the_charge(self, db_session):
        """One missed month is an outlying gap, and the spread measure is robust."""
        for date in _from("2026-01-09", [0, 30, 61, 122, 152, 183]):
            _add_charge(db_session, "MUSIC STREAM", -40.0, date)
        db_session.commit()

        item = RecurringService(db_session).get_recurring(
            today=pd.Timestamp("2026-07-15")
        )["items"][0]
        assert item["cadence"] == "monthly"
        assert item["occurrences"] == 6


class TestConfidence:
    """Every candidate carries how much evidence backs it."""

    def test_an_alternating_rhythm_is_ranked_down_not_dropped(self, db_session):
        """A strictly alternating 26/34-day rhythm scores below a steady one.

        The robust spread reads an alternating rhythm as *perfectly* regular —
        most gaps sit exactly on the median — so the interquartile term is what
        notices the split. A genuine payment can alternate, so this ranks the
        candidate down for the reviewer rather than discarding it.
        """
        for date in _from("2026-01-01", [0, 26, 60, 86, 120, 146]):
            _add_charge(db_session, "CORNER BAKERY", -60.0, date, category="Food")
        for date in _from("2026-01-03", [0, 30, 61, 91, 122, 152]):
            _add_charge(db_session, "STEADY CLUB", -60.0, date)
        db_session.commit()

        items = RecurringService(db_session).get_recurring(
            today=pd.Timestamp("2026-06-10")
        )["items"]
        scores = {item["label"]: item["confidence"] for item in items}
        assert scores["CORNER BAKERY"] < scores["STEADY CLUB"]

    def test_a_textbook_subscription_scores_high(self, db_session):
        """Same day, same amount, eight times over: near-total confidence."""
        for n in range(8):
            _add_charge(db_session, "NETFLIX.COM 1234", -45.0, _months_ago(n))
        db_session.commit()

        item = RecurringService(db_session).get_recurring()["items"][0]
        assert item["confidence"] >= 0.9
        assert item["amount_kind"] == "fixed"

    def test_thin_evidence_scores_lower_than_a_long_history(self, db_session):
        """Two identical patterns rank by how many times each has been seen.

        Confidence is what lets the review list put the obvious cases first
        instead of hiding the marginal ones outright.
        """
        for n in range(12):
            _add_charge(db_session, "LONG RUNNING", -45.0, _months_ago(n))
        for n in range(3):
            _add_charge(db_session, "JUST STARTED", -45.0, _months_ago(n))
        db_session.commit()

        items = RecurringService(db_session).get_recurring(
            today=_day_after_last_charge()
        )["items"]
        scores = {item["label"]: item["confidence"] for item in items}
        assert scores["JUST STARTED"] < scores["LONG RUNNING"]
