"""Unit tests for SavingsGoalService — CRUD, lifecycle, money in and out, and derived metrics.

A goal holds what the user put into it (entries), plus its own income, less
what it paid for. These tests mostly drive goals through ``initial_amount``
and entries with no transactions, so the enrichment maths is isolated; the
replay of entries against transactions lives in ``test_savings_goal_ledger.py``.
"""

from datetime import date

import pandas as pd
import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    ENTRY_CLOSE,
    ENTRY_COVER,
    ENTRY_MANUAL,
    LINK_CONTRIBUTION,
    SavingsGoal,
)
from backend.repositories.savings_goal_repository import SavingsGoalRepository
from backend.services.savings_goals import DAYS_PER_MONTH, SavingsGoalService
from tests.backend.unit.services.savings_goal_helpers import (
    add_txn,
    month_str,
    seed_liquid,
)


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
    treated as two full months when only ~39 days remain.
    """
    today = pd.Timestamp.today().normalize()
    target = pd.Timestamp(target_date)
    return max(0, (target - today).days) / DAYS_PER_MONTH


def _months_ahead(months: int) -> str:
    """Return a ``YYYY-MM-DD`` date ``months`` months from today."""
    return (pd.Timestamp.today().normalize() + pd.DateOffset(months=months)).strftime(
        "%Y-%m-%d"
    )


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


def _only(goals: list[dict]) -> dict:
    """Return the single goal in a service response."""
    assert len(goals) == 1
    return goals[0]


def _by_name(goals: list[dict]) -> dict[str, dict]:
    """Index a goal list by name."""
    return {g["name"]: g for g in goals}


class TestSavingsGoalServiceCrud:
    """Tests for create/update/delete/get_all behaviour."""

    def test_get_all_empty_returns_empty_list(self, service):
        """A fresh DB yields an empty list, not an empty DataFrame."""
        assert service.get_all() == []

    def test_create_with_initial_amount_records_an_entry(self, service):
        """The initial amount is the goal's first entry, dated today."""
        goal = _only(
            service.create(name="Vacation", target_amount=1000, initial_amount=250)
        )

        assert goal["name"] == "Vacation"
        assert goal["added"] == 250
        assert goal["saved"] == 250
        assert goal["balance"] == 250
        assert goal["available"] == 250
        assert goal["remaining"] == 750
        assert goal["progress_pct"] == 25.0
        assert goal["is_achieved"] is False
        assert len(goal["entries"]) == 1
        entry = goal["entries"][0]
        assert entry["amount"] == 250
        assert entry["source"] == ENTRY_MANUAL
        assert entry["date"] == date.today().isoformat()

    def test_create_without_initial_amount_has_no_entries(self, service):
        """A goal created empty holds nothing and lists no entries."""
        goal = _only(service.create(name="Vacation", target_amount=1000))

        assert goal["entries"] == []
        assert goal["available"] == 0
        assert goal["added_this_month"] == 0

    def test_create_defaults_priority_to_the_bottom(self, service):
        """Each new goal is appended to the end of the list."""
        service.create(name="First", target_amount=1000)
        goals = _by_name(service.create(name="Second", target_amount=1000))

        assert goals["First"]["priority"] < goals["Second"]["priority"]

    def test_create_defaults_start_month_to_this_month(self, service):
        """A new goal never claims transactions from months that predate it."""
        goal = _only(service.create(name="Vacation", target_amount=1000))
        today = date.today()
        assert goal["start_month"] == f"{today.year:04d}-{today.month:02d}"

    def test_create_rejects_an_unparseable_start_month(self, service):
        """A malformed start month is refused rather than silently ignored."""
        with pytest.raises(ValidationException):
            service.create(name="Vacation", target_amount=1000, start_month="nope")

    def test_create_refuses_income_another_goal_already_claims(self, service):
        """One income can feed only one goal."""
        service.create(
            name="Wedding", target_amount=1000, contribution_category="Other Income"
        )
        with pytest.raises(ValidationException):
            service.create(
                name="Trip", target_amount=1000, contribution_category="Other Income"
            )

    def test_update_changes_fields(self, service):
        """Updating a goal restates its derived metrics."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        updated = _only(
            service.update(
                created["id"], target_amount=2000, name="Trip", monthly_amount=300
            )
        )

        assert updated["name"] == "Trip"
        assert updated["target_amount"] == 2000
        assert updated["monthly_amount"] == 300

    def test_update_with_none_clears_monthly_amount(self, service):
        """``None`` clears an optional column."""
        created = _only(
            service.create(name="Vacation", target_amount=1000, monthly_amount=300)
        )

        updated = _only(service.update(created["id"], monthly_amount=None))

        assert updated["monthly_amount"] is None

    def test_update_missing_raises_not_found(self, service):
        """Updating an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.update(9999, name="nope")

    def test_delete_removes_goal_and_its_entries(self, db_session, service):
        """A deleted goal disappears with every entry it had."""
        created = _only(
            service.create(name="Vacation", target_amount=1000, initial_amount=100)
        )

        service.delete(created["id"])

        assert service.get_all() == []
        assert SavingsGoalRepository(db_session).get_entries().empty

    def test_delete_missing_raises_not_found(self, service):
        """Deleting an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.delete(9999)

    def test_get_all_orders_by_priority(self, service):
        """Goals come back in list order, not insertion order."""
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
    """Closing hands the goal's money back; reopening restores it."""

    def test_close_marks_the_goal_and_stamps_the_month(self, service):
        """Closing records when it happened."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        closed = _only(service.close(created["id"]))

        today = date.today()
        assert closed["is_closed"] is True
        assert closed["closed_month"] == f"{today.year:04d}-{today.month:02d}"

    def test_close_hands_what_it_holds_back_as_a_close_entry(self, db_session, service):
        """The goal is emptied by a ``close`` entry and free cash grows by as much."""
        seed_liquid(db_session, 1000)
        created = _only(
            service.create(name="Vacation", target_amount=1000, initial_amount=300)
        )
        assert service.get_free_cash()["free_cash"] == 700

        closed = _only(service.close(created["id"]))

        assert closed["available"] == 0
        assert closed["balance"] == 0
        close_entries = [e for e in closed["entries"] if e["source"] == ENTRY_CLOSE]
        assert [e["amount"] for e in close_entries] == [-300]
        assert service.get_free_cash()["free_cash"] == 1000

    def test_close_of_an_empty_goal_writes_no_entry(self, service):
        """Nothing held, nothing handed back."""
        created = _only(service.create(name="Vacation", target_amount=1000))

        closed = _only(service.close(created["id"]))

        assert closed["entries"] == []

    def test_reopen_restores_what_closing_handed_back(self, db_session, service):
        """Reopening deletes the close entry, so the goal holds its money again."""
        seed_liquid(db_session, 1000)
        created = _only(
            service.create(name="Vacation", target_amount=1000, initial_amount=300)
        )
        service.close(created["id"])

        reopened = _only(service.reopen(created["id"]))

        assert reopened["is_closed"] is False
        assert reopened["closed_month"] is None
        assert reopened["available"] == 300
        assert all(e["source"] != ENTRY_CLOSE for e in reopened["entries"])
        assert service.get_free_cash()["free_cash"] == 700

    def test_close_missing_raises_not_found(self, service):
        """Closing an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.close(9999)

    def test_reopen_missing_raises_not_found(self, service):
        """Reopening an unknown goal surfaces a 404-mapped exception."""
        with pytest.raises(EntityNotFoundException):
            service.reopen(9999)


class TestEntries:
    """Putting money into a goal and taking it out."""

    def test_add_and_take_out(self, service):
        """A positive entry adds, a negative one takes back; both are listed newest first."""
        goal = _only(service.create(name="Trip", target_amount=1000))
        today = date.today().isoformat()

        service.add_entry(goal["id"], 400, entry_date=today, note="bonus")
        after = _only(service.add_entry(goal["id"], -150, entry_date=today))

        assert after["added"] == 250
        assert after["available"] == 250
        assert after["added_this_month"] == 250
        assert [e["amount"] for e in after["entries"]] == [-150, 400]
        assert after["entries"][1]["note"] == "bonus"

    def test_entry_date_defaults_to_today(self, service):
        """An entry without a date lands today."""
        goal = _only(service.create(name="Trip", target_amount=1000))

        after = _only(service.add_entry(goal["id"], 100))

        assert after["entries"][0]["date"] == date.today().isoformat()

    def test_taking_out_more_than_held_is_refused(self, service):
        """A goal cannot hand back money it does not hold."""
        goal = _only(
            service.create(name="Trip", target_amount=1000, initial_amount=100)
        )

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], -100.01)

    def test_taking_out_everything_held_is_allowed(self, service):
        """Emptying a goal exactly is fine."""
        goal = _only(
            service.create(name="Trip", target_amount=1000, initial_amount=100)
        )

        after = _only(service.add_entry(goal["id"], -100))

        assert after["available"] == 0

    def test_zero_amount_is_refused(self, service):
        """An entry has to move money."""
        goal = _only(service.create(name="Trip", target_amount=1000))

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], 0)

    def test_unparseable_date_is_refused(self, service):
        """A malformed date is refused rather than stored."""
        goal = _only(service.create(name="Trip", target_amount=1000))

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], 100, entry_date="tomorrow")

    def test_closed_goal_takes_no_entries(self, service):
        """Money cannot move into or out of a closed goal."""
        goal = _only(service.create(name="Trip", target_amount=1000))
        service.close(goal["id"])

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], 100)

    def test_entry_on_unknown_goal_raises_not_found(self, service):
        """An entry needs a goal to belong to."""
        with pytest.raises(EntityNotFoundException):
            service.add_entry(9999, 100)

    def test_delete_entry_undoes_it(self, service):
        """Deleting an entry takes its money back out of the goal."""
        goal = _only(
            service.create(name="Trip", target_amount=1000, initial_amount=100)
        )
        added = _only(service.add_entry(goal["id"], 300))
        entry_id = next(e["id"] for e in added["entries"] if e["amount"] == 300)

        after = _only(service.delete_entry(entry_id))

        assert after["available"] == 100
        assert [e["amount"] for e in after["entries"]] == [100]

    def test_delete_unknown_entry_raises_not_found(self, service):
        """Deleting an entry that does not exist surfaces a 404."""
        with pytest.raises(EntityNotFoundException):
            service.delete_entry(9999)


class TestFund:
    """Funding puts the month's suggestion in, top of the list first, within free cash."""

    def test_fund_puts_each_suggestion_in(self, db_session, service):
        """Every goal with a suggestion gets it."""
        seed_liquid(db_session, 10000)
        service.create(name="A", target_amount=5000, monthly_amount=500)
        service.create(name="B", target_amount=5000, monthly_amount=200)

        goals = _by_name(service.fund())

        assert goals["A"]["added_this_month"] == 500
        assert goals["B"]["added_this_month"] == 200
        assert goals["A"]["suggested_this_month"] == 0
        assert service.get_free_cash()["free_cash"] == 9300

    def test_fund_stops_when_free_cash_runs_out(self, db_session, service):
        """Lower goals get nothing rather than driving free cash negative."""
        seed_liquid(db_session, 600)
        service.create(name="A", target_amount=5000, monthly_amount=500)
        service.create(name="B", target_amount=5000, monthly_amount=500)

        goals = _by_name(service.fund())

        assert goals["A"]["available"] == 500
        assert goals["B"]["available"] == 100
        assert service.get_free_cash()["free_cash"] == 0

    def test_fund_only_the_goals_asked_for(self, db_session, service):
        """``goal_ids`` limits which goals are funded."""
        seed_liquid(db_session, 10000)
        service.create(name="A", target_amount=5000, monthly_amount=500)
        b = _by_name(service.create(name="B", target_amount=5000, monthly_amount=200))[
            "B"
        ]

        goals = _by_name(service.fund([b["id"]]))

        assert goals["A"]["available"] == 0
        assert goals["B"]["available"] == 200

    def test_fund_with_no_free_cash_adds_nothing(self, service):
        """With nothing free, funding is a no-op."""
        service.create(name="A", target_amount=5000, monthly_amount=500)

        goal = _only(service.fund())

        assert goal["entries"] == []


class TestCover:
    """A free-cash shortfall is covered from the lowest goals first."""

    def test_plan_takes_from_the_lowest_goal_first(self, db_session, service):
        """The bottom goal gives back before the one above it."""
        seed_liquid(db_session, 1000)
        service.create(name="Top", target_amount=5000, initial_amount=800)
        service.create(name="Bottom", target_amount=5000, initial_amount=700)

        plan = service.cover_plan()

        assert [(step["name"], step["amount"]) for step in plan] == [("Bottom", 500)]

    def test_plan_moves_up_when_the_lowest_goal_runs_dry(self, db_session, service):
        """No goal gives more than it holds."""
        seed_liquid(db_session, 700)
        service.create(name="Top", target_amount=5000, initial_amount=900)
        service.create(name="Bottom", target_amount=5000, initial_amount=300)

        plan = service.cover_plan()

        assert [(step["name"], step["amount"]) for step in plan] == [
            ("Bottom", 300),
            ("Top", 200),
        ]

    def test_no_shortfall_means_no_plan(self, db_session, service):
        """Positive free cash needs no cover."""
        seed_liquid(db_session, 1000)
        service.create(name="Top", target_amount=5000, initial_amount=300)

        assert service.cover_plan() == []

    def test_cover_applies_the_plan_as_cover_entries(self, db_session, service):
        """After covering, free cash is back at zero."""
        seed_liquid(db_session, 700)
        service.create(name="Top", target_amount=5000, initial_amount=900)
        service.create(name="Bottom", target_amount=5000, initial_amount=300)

        goals = _by_name(service.cover())

        assert goals["Bottom"]["available"] == 0
        assert goals["Top"]["available"] == 700
        assert [e["source"] for e in goals["Bottom"]["entries"]][0] == ENTRY_COVER
        free = service.get_free_cash()
        assert free["free_cash"] == 0
        assert free["cover_plan"] == []


class TestContributionLinks:
    """Only money coming in can be saved into a goal."""

    def test_outgoing_transaction_cannot_be_a_contribution(self, db_session, service):
        """Setting money aside is an entry, not a link."""
        goal = _only(service.create(name="Trip", target_amount=1000))
        txn = add_txn(db_session, month_str(0), -500, "Food", day=1)

        with pytest.raises(ValidationException):
            service.link_transaction(
                goal["id"],
                "transaction",
                txn.unique_id,
                "bank_transactions",
                LINK_CONTRIBUTION,
            )

    def test_incoming_transaction_counts_as_income(self, db_session, service):
        """A linked gift is the goal's income and counts toward its target."""
        goal = _only(service.create(name="Trip", target_amount=1000))
        txn = add_txn(db_session, month_str(0), 400, "Other Income", day=1)

        linked = _only(
            service.link_transaction(
                goal["id"],
                "transaction",
                txn.unique_id,
                "bank_transactions",
                LINK_CONTRIBUTION,
            )
        )

        assert linked["income"] == 400
        assert linked["saved"] == 400
        assert linked["available"] == 400


class TestSavingsGoalEnrichment:
    """Tests for the derived progress metrics attached to each goal."""

    def test_zero_target_yields_zero_progress(self, db_session, service):
        """A zero target can't divide, so progress stays at 0 rather than NaN."""
        db_session.add(SavingsGoal(name="Zero", target_amount=0))
        db_session.commit()
        goal_id = _only(service.get_all())["id"]
        SavingsGoalRepository(db_session).add_entry(
            goal_id, date.today().isoformat(), 100, ENTRY_MANUAL
        )

        goal = _only(SavingsGoalService(db_session).get_all())
        assert goal["progress_pct"] == 0.0
        assert goal["is_achieved"] is False

    def test_overshoot_caps_progress_at_100(self, service):
        """Saving past the target caps the bar without capping the amount."""
        goal = _only(
            service.create(name="Over", target_amount=1000, initial_amount=1500)
        )

        assert goal["progress_pct"] == 100.0
        assert goal["saved"] == 1500
        assert goal["remaining"] == 0
        assert goal["is_achieved"] is True

    def test_taking_money_out_lowers_progress(self, service):
        """Saved is net of what was taken back out."""
        goal = _only(
            service.create(name="Trip", target_amount=1000, initial_amount=600)
        )

        after = _only(service.add_entry(goal["id"], -200))

        assert after["saved"] == 400
        assert after["remaining"] == 600
        assert after["progress_pct"] == 40.0

    def test_future_target_date_sets_monthly_needed(self, service):
        """A dated goal reports the contribution needed over its real runway."""
        target_date = _months_ahead(5)
        goal = _only(
            service.create(name="Trip", target_amount=1000, target_date=target_date)
        )

        assert goal["months_remaining"] == _months_until(target_date)
        assert goal["monthly_needed"] == pytest.approx(
            round(1000 / _runway_months_until(target_date), 2)
        )

    def test_past_target_date_needs_full_remaining_now(self, service):
        """An overdue goal asks for everything that is left, immediately."""
        past = _months_ahead(-2)
        goal = _only(
            service.create(
                name="Late", target_amount=1000, initial_amount=200, target_date=past
            )
        )

        assert goal["months_remaining"] == 0
        assert goal["monthly_needed"] == 800
        assert goal["is_past_due"] is True

    def test_achieved_goal_has_no_monthly_needed(self, service):
        """Nothing more is needed once the target is met."""
        goal = _only(
            service.create(
                name="Done",
                target_amount=1000,
                initial_amount=1000,
                target_date=_months_ahead(3),
            )
        )

        assert goal["is_achieved"] is True
        assert goal["monthly_needed"] is None
        assert goal["is_past_due"] is False

    def test_no_target_date_has_no_time_metrics(self, service):
        """A dateless goal reports progress but no schedule."""
        goal = _only(
            service.create(name="Someday", target_amount=1000, initial_amount=100)
        )

        assert goal["months_remaining"] is None
        assert goal["monthly_needed"] is None
        assert goal["is_past_due"] is False


class TestSuggestedThisMonth:
    """What the card suggests putting into a goal this month."""

    def test_monthly_amount_is_the_suggestion(self, service):
        """A goal with a monthly amount suggests exactly that."""
        goal = _only(
            service.create(name="Trip", target_amount=5000, monthly_amount=500)
        )

        assert goal["suggested_this_month"] == 500

    def test_money_added_this_month_counts_toward_the_suggestion(self, service):
        """Adding part of the month's amount leaves the rest suggested."""
        goal = _only(
            service.create(name="Trip", target_amount=5000, monthly_amount=500)
        )

        after = _only(service.add_entry(goal["id"], 200))

        assert after["added_this_month"] == 200
        assert after["suggested_this_month"] == 300

    def test_suggestion_never_exceeds_what_is_left(self, service):
        """A goal 300 short never asks for its full monthly amount."""
        goal = _only(service.create(name="Trip", target_amount=300, monthly_amount=500))

        assert goal["suggested_this_month"] == 300

    def test_target_date_drives_the_suggestion_without_a_monthly_amount(self, service):
        """Remaining over the runway; funding part of it lowers it by as much."""
        target_date = _months_ahead(5)
        goal = _only(
            service.create(name="Trip", target_amount=1000, target_date=target_date)
        )
        runway = _runway_months_until(target_date)
        assert goal["suggested_this_month"] == pytest.approx(1000 / runway, abs=0.01)

        after = _only(service.add_entry(goal["id"], 50))

        assert after["suggested_this_month"] == pytest.approx(
            1000 / runway - 50, abs=0.01
        )

    def test_no_monthly_amount_and_no_date_suggests_nothing(self, service):
        """Without a plan there is nothing to suggest."""
        goal = _only(service.create(name="Someday", target_amount=1000))

        assert goal["suggested_this_month"] == 0

    def test_achieved_and_closed_goals_suggest_nothing(self, service):
        """A full or closed goal needs no more money."""
        service.create(
            name="Full", target_amount=100, initial_amount=100, monthly_amount=50
        )
        closed = _by_name(
            service.create(name="Closed", target_amount=1000, monthly_amount=50)
        )["Closed"]

        goals = _by_name(service.close(closed["id"]))

        assert goals["Full"]["suggested_this_month"] == 0
        assert goals["Closed"]["suggested_this_month"] == 0


class TestRunwayUsesRealDays:
    """`monthly_needed` is sized off days remaining, not whole calendar months."""

    def test_monthly_needed_accounts_for_partial_first_month(self, service):
        """A goal due early next month asks for more than a naive month split."""
        target_ts = (
            pd.Timestamp.today().normalize() + pd.DateOffset(months=2)
        ).replace(day=1)
        target_date = target_ts.strftime("%Y-%m-%d")
        goal = _only(
            service.create(name="Soon", target_amount=1000, target_date=target_date)
        )

        runway = _runway_months_until(target_date)
        assert goal["monthly_needed"] == pytest.approx(round(1000 / runway, 2))
        # The calendar-month count would understate the required contribution.
        assert goal["monthly_needed"] > 1000 / max(1, _months_until(target_date))


class TestReadModels:
    """Shapes of free cash, the month view and the timeline."""

    def test_free_cash_without_goals(self, service):
        """No goals, nothing earmarked."""
        assert service.get_free_cash() == {
            "free_cash": 0.0,
            "earmarked": 0.0,
            "liquid": 0.0,
            "has_goals": False,
            "shortfall": 0.0,
            "cover_plan": [],
        }

    def test_free_cash_is_liquid_less_what_goals_hold(self, db_session, service):
        """Bank money and transactions, less every goal's balance."""
        seed_liquid(db_session, 1000)
        add_txn(db_session, month_str(0), 500, "Salary", day=1)
        service.create(name="Trip", target_amount=5000, initial_amount=1800)

        free = service.get_free_cash()

        assert free["liquid"] == 1500
        assert free["earmarked"] == 1800
        assert free["free_cash"] == -300
        assert free["shortfall"] == 300
        assert free["has_goals"] is True
        assert free["cover_plan"][0]["amount"] == 300

    def test_month_lists_what_moved(self, service):
        """The current month shows the entries made in it."""
        goal = _only(
            service.create(name="Trip", target_amount=5000, initial_amount=250)
        )
        today = date.today()

        month = service.get_month(today.year, today.month)

        assert month["total_added"] == 250
        assert month["total_change"] == 250
        assert month["goals"] == [
            {
                "goal_id": goal["id"],
                "name": "Trip",
                "priority": goal["priority"],
                "status": "active",
                "added": 250,
                "income": 0,
                "spent": 0,
                "change": 250,
            }
        ]

    def test_month_without_movement_is_empty(self, service):
        """A month nothing moved in lists no goals."""
        service.create(name="Trip", target_amount=5000)

        month = service.get_month(2000, 1)

        assert month["goals"] == []
        assert month["total_added"] == 0

    def test_timeline_reports_each_goal_per_month(self, db_session, service):
        """Each month carries free cash and every goal's balance and change."""
        seed_liquid(db_session, 1000)
        goal = _only(
            service.create(name="Trip", target_amount=5000, initial_amount=400)
        )

        timeline = service.get_timeline()

        assert timeline["has_goals"] is True
        assert timeline["goals"][0]["id"] == goal["id"]
        last = timeline["months"][-1]
        today = date.today()
        assert last["month"] == f"{today.year:04d}-{today.month:02d}"
        assert last["free_cash"] == 600
        assert last["goals"] == [{"goal_id": goal["id"], "balance": 400, "change": 400}]
