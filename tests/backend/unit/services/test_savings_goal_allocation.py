"""Unit tests for the savings-goal allocation engine.

Covers the waterfall itself — priority order, per-goal monthly caps, spillover
— plus the rules that surround it: contributions consuming the month's surplus
before the waterfall runs, utilizations drawing a goal down without touching
its target, negative-surplus months draining the free-cash pool before they
reach any goal, auto-closure, and the immutability of a closed goal's history
across a rebuild.
"""

import math
from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
)
from backend.models.bank_balance import BankBalance
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.budget.project import ProjectBudgetService
from backend.services.savings_goals import SavingsGoalService
from backend.services.tagging_service import CategoriesTagsService


def _month_str(offset_back: int) -> str:
    """Return ``YYYY-MM`` for the month ``offset_back`` months before now."""
    today = date.today()
    month = today.month - offset_back
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def _day_in_month(month: str, day: int = 15) -> str:
    """Return a ``YYYY-MM-DD`` date inside the given ``YYYY-MM`` month."""
    return f"{month}-{day:02d}"


def _add_txn(db, month: str, amount: float, category: str, tag: str = None, day: int = 15):
    """Insert one bank transaction into a month and return it."""
    txn = BankTransaction(
        id=f"t-{month}-{amount}-{day}",
        date=_day_in_month(month, day),
        provider="TestBank",
        account_name="Main",
        description="test",
        amount=amount,
        category=category,
        tag=tag,
        source="bank_transactions",
        type="normal",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def _seed_surplus(db, month: str, income: float, expenses: float) -> None:
    """Give a month a known realized surplus of ``income - expenses``."""
    _add_txn(db, month, income, "Salary", day=1)
    _add_txn(db, month, -expenses, "Food", day=2)


def _seed_free_cash(db, amount: float) -> None:
    """Give the user ``amount`` of liquid money from before tracking began.

    Bank prior wealth is what seeds the free-cash pool, so this is how a test
    says "there was already money in the account".
    """
    db.add(
        BankBalance(
            provider="TestBank",
            account_name="Main",
            balance=amount,
            prior_wealth_amount=amount,
        )
    )
    db.commit()


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


class TestWaterfallOrdering:
    """Priority decides who is funded first, and leftovers spill downward."""

    def test_surplus_runs_out_before_lower_priority_goal(self, db_session, service):
        """A goal below the waterline gets nothing when the surplus is exhausted."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)

        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["First"]["funded"] == 500
        assert goals["Second"]["funded"] == 0

    def test_goal_never_takes_more_than_it_needs(self, db_session, service):
        """A goal stops at its target and the remainder flows to the next one."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)

        service.create(name="Small", target_amount=200, priority=0, start_month=last)
        service.create(name="Big", target_amount=5000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Small"]["funded"] == 200
        assert goals["Big"]["funded"] == 2800


class TestMonthlyCap:
    """A per-goal monthly ceiling limits how fast one goal can absorb surplus."""

    def test_cap_limits_monthly_intake_and_spills_over(self, db_session, service):
        """Once a goal hits its cap the rest of the pool moves down the list."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)

        service.create(
            name="Capped", target_amount=5000, priority=0, monthly_cap=500,
            start_month=last,
        )
        service.create(name="Next", target_amount=5000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Capped"]["funded"] == 500
        assert goals["Next"]["funded"] == 2500

    def test_cap_accumulates_across_months(self, db_session, service):
        """A capped goal keeps taking its cap every month until it fills."""
        for offset in (3, 2, 1):
            _seed_surplus(db_session, _month_str(offset), income=10000, expenses=9000)

        service.create(
            name="Capped", target_amount=5000, priority=0, monthly_cap=400,
            start_month=_month_str(3),
        )

        goal = service.get_all()[0]
        assert goal["funded"] == 1600


class TestAchievement:
    """A goal that filled reads as achieved, float error notwithstanding."""

    def test_goal_filled_across_many_months_reads_achieved(self, db_session, service):
        """Summing dozens of rows must not leave a full goal a hair short.

        `funded` is accumulated row by row, so a goal filled over many capped
        months can land microscopically under its target. Rounded for display
        it reads "100%, 0 to go" — it must not also read "not achieved", and
        it must still be able to auto-close.
        """
        months = [_month_str(i) for i in range(1, 13)]
        for month in months:
            _seed_surplus(db_session, month, income=10000, expenses=9000)

        # 12 months x 1000 surplus, capped at 333.33 -> a target only float
        # accumulation can miss.
        service.create(
            name="Goal",
            target_amount=3999.96,
            priority=0,
            monthly_cap=333.33,
            start_month=months[-1],
        )

        goal = service.get_all()[0]
        assert goal["progress_pct"] == 100.0
        assert goal["remaining"] == 0
        assert goal["is_achieved"] is True


class TestSurplusDefinition:
    """What counts as the month's spare money."""

    def test_investment_transfers_reduce_the_surplus(self, db_session, service):
        """Money moved into investments has left the spendable pool."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        _add_txn(db_session, last, -2000, "Investments", day=3)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=last)

        assert service.get_all()[0]["funded"] == 1000

    def test_a_late_goal_takes_the_free_cash_waiting_when_it_starts(
        self, db_session, service
    ):
        """Nothing is allocated before its start; then the waiting pool fills it.

        Free cash is there to fill goals: money that built up before a goal
        started is handed to it in its start month, never left idle.
        """
        _seed_surplus(db_session, _month_str(3), income=10000, expenses=5000)
        _seed_surplus(db_session, _month_str(1), income=10000, expenses=9800)

        service.create(
            name="Late", target_amount=5000, priority=0, start_month=_month_str(1)
        )

        assert service.get_all()[0]["funded"] == 5000
        months = {m["month"]: m for m in service.get_timeline(months=0)["months"]}
        assert months[_month_str(1)]["goals"][0]["allocated"] == 5000


class TestExplicitContributions:
    """Linked contributions consume the pool before the waterfall runs."""

    def test_contribution_funds_its_goal_and_shrinks_the_pool(
        self, db_session, service
    ):
        """A tagged transfer credits its goal and leaves less for everyone else."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        transfer = _add_txn(db_session, last, -800, "Other", day=4)

        service.create(name="Top", target_amount=5000, priority=0, start_month=last)
        created = service.create(
            name="Linked", target_amount=5000, priority=1, start_month=last
        )
        linked_id = next(g["id"] for g in created if g["name"] == "Linked")

        service.link_transaction(
            goal_id=linked_id,
            source_type="transaction",
            source_id=transfer.unique_id,
            source_table="bank_transactions",
            link_type=LINK_CONTRIBUTION,
        )

        goals = {g["name"]: g for g in service.get_all()}
        # Linking pulls the 800 out of the expense side (surplus rises to 3000)
        # and hands it straight to its goal, which consumes it before the
        # waterfall runs. Top keeps the 2200 it was already allocated.
        assert goals["Linked"]["contributed"] == 800
        assert goals["Linked"]["funded"] == 800
        assert goals["Top"]["funded"] == 2200

    def test_category_rule_accrues_contributions_automatically(
        self, db_session, service
    ):
        """A goal with a contribution category picks up matching transactions."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        _add_txn(db_session, last, -600, "Savings", tag="Vacation", day=5)

        service.create(
            name="Vacation",
            target_amount=5000,
            priority=0,
            start_month=last,
            contribution_category="Savings",
        )

        goal = service.get_all()[0]
        assert goal["contributed"] == 600
        # A saved-into rule does not take the goal out of the waterfall: the
        # month's other 2400 of surplus fills it too.
        assert goal["allocated"] == 2400
        assert goal["funded"] == 3000
        assert service.get_free_cash()["free_cash"] == 0

    def test_incoming_contribution_is_new_money_not_a_draw_on_the_pool(
        self, db_session, service
    ):
        """A gift earmarked for a goal funds it without being clawed back.

        Income linked to a goal arrives already earmarked: it never passed
        through the free-cash pool, so it must not be charged against it.
        Charging it drove the pool negative by the size of the gift, and the
        clawback then took the gift straight back out of the goal it funded.
        """
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        _add_txn(db_session, last, 100000, "Other Income", tag="Wedding", day=6)

        service.create(
            name="Wedding",
            target_amount=100000,
            priority=0,
            start_month=last,
            contribution_category="Other Income",
            contribution_tags="Wedding",
        )
        service.create(name="Trip", target_amount=5000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Wedding"]["contributed"] == 100000
        assert goals["Wedding"]["clawed_back"] == 0
        assert goals["Wedding"]["funded"] == 100000
        # The gift covers its goal, so the month's own surplus is still there
        # for the next goal in line.
        assert goals["Trip"]["funded"] == 3000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["liquid"] == 103000

    def test_incoming_contribution_past_the_target_spills_down_the_waterfall(
        self, db_session, service
    ):
        """A goal keeps only what it needs of a gift; the rest is surplus."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        _add_txn(db_session, last, 100000, "Other Income", tag="Wedding", day=6)

        service.create(
            name="Wedding",
            target_amount=60000,
            priority=0,
            start_month=last,
            contribution_category="Other Income",
            contribution_tags="Wedding",
        )
        service.create(name="Trip", target_amount=30000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Wedding"]["contributed"] == 60000
        assert goals["Wedding"]["funded"] == 60000
        # 40000 of spilled gift plus the month's own 3000 surplus.
        assert goals["Trip"]["funded"] == 30000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 13000
        assert pool["liquid"] == 103000
        month = service.get_month_allocations(*map(int, last.split("-")))
        wedding = next(row for row in month["goals"] if row["name"] == "Wedding")
        assert wedding["contributed"] == 60000


class TestUtilization:
    """Spending out of a goal draws it down without moving its target."""

    def test_utilization_reduces_available_but_not_target(self, db_session, service):
        """Buying the thing you saved for lowers `available`, never `target_amount`."""
        earlier, last = _month_str(2), _month_str(1)
        _seed_surplus(db_session, earlier, income=10000, expenses=9000)
        _seed_surplus(db_session, last, income=10000, expenses=9800)
        spend = _add_txn(db_session, last, -400, "Travel", day=6)

        created = service.create(
            name="Trip", target_amount=1000, priority=0, start_month=earlier
        )
        goal_id = created[0]["id"]
        service.link_transaction(
            goal_id=goal_id,
            source_type="transaction",
            source_id=spend.unique_id,
            source_table="bank_transactions",
            link_type=LINK_UTILIZATION,
        )

        goal = service.get_all()[0]
        assert goal["target_amount"] == 1000
        assert goal["utilized"] == 400
        assert goal["available"] == round(goal["funded"] - 400, 2)

    def test_goal_closes_when_achieved_and_fully_spent(self, db_session, service):
        """A filled goal whose money is all spent stops absorbing surplus."""
        earlier, last = _month_str(2), _month_str(1)
        _seed_surplus(db_session, earlier, income=10000, expenses=9000)
        _seed_surplus(db_session, last, income=10000, expenses=9000)

        created = service.create(
            name="Trip", target_amount=1000, priority=0, start_month=earlier
        )
        goal_id = created[0]["id"]
        spend = _add_txn(db_session, last, -1000, "Travel", day=6)
        service.link_transaction(
            goal_id=goal_id,
            source_type="transaction",
            source_id=spend.unique_id,
            source_table="bank_transactions",
            link_type=LINK_UTILIZATION,
        )

        goal = service.get_all()[0]
        assert goal["is_closed"] is True
        assert goal["status"] == GOAL_STATUS_CLOSED
        assert goal["closed_month"] == last


def _add_card_txn(db, month: str, amount: float, category: str, day: int = 15):
    """Insert one itemized credit-card purchase into a month and return it."""
    txn = CreditCardTransaction(
        id=f"cc-{month}-{amount}-{day}",
        date=_day_in_month(month, day),
        provider="TestCard",
        account_name="Card",
        description="test",
        amount=amount,
        category=category,
        source="credit_card_transactions",
        type="normal",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def _create_project(db, name: str, budget: float = 50000) -> None:
    """Create a project budget over a fresh category."""
    CategoriesTagsService(db).add_category(name, ["Venue"])
    ProjectBudgetService(db).create_project(name, budget)


class TestSpendingLink:
    """A goal pays for a project, an envelope or any category/tags with one link."""

    def test_project_spend_is_utilized_without_touching_the_pool(
        self, db_session, service
    ):
        """Every project purchase draws the goal down; the surplus ignores them."""
        earlier, last = _month_str(2), _month_str(1)
        _seed_surplus(db_session, earlier, income=10000, expenses=8000)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_txn(db_session, last, -700, "Wedding", tag="Venue", day=6)
        _add_txn(db_session, last, -300, "Wedding", day=7)

        created = service.create(
            name="Wedding fund", target_amount=5000, priority=0, start_month=earlier
        )
        liquid = service.get_free_cash()["liquid"]
        goal = service.set_spending_link(created[0]["id"], "Wedding")[0]

        assert goal["utilization_category"] == "Wedding"
        assert goal["utilized"] == 1000
        # History keeps its rows, so the goal's funding stands; the project's
        # 1000 now comes out of the goal instead of out of free cash.
        assert goal["funded"] == 4000
        assert goal["available"] == 3000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["liquid"] == liquid

    def test_refund_nets_against_the_project_spend(self, db_session, service):
        """A refund in the project's category hands money back to the goal."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_txn(db_session, last, -1000, "Wedding", day=6)
        _add_txn(db_session, last, 250, "Wedding", day=9)

        created = service.create(
            name="Wedding fund", target_amount=5000, priority=0, start_month=last
        )
        goal = service.set_spending_link(created[0]["id"], "Wedding")[0]

        assert goal["utilized"] == 750

    def test_spend_before_the_goal_started_stays_an_expense(
        self, db_session, service
    ):
        """Purchases that predate the goal were never paid out of it."""
        earlier, last = _month_str(2), _month_str(1)
        _seed_surplus(db_session, earlier, income=10000, expenses=8000)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_txn(db_session, earlier, -600, "Wedding", day=6)
        _add_txn(db_session, last, -400, "Wedding", day=6)

        created = service.create(
            name="Wedding fund", target_amount=5000, priority=0, start_month=last
        )
        goal = service.set_spending_link(created[0]["id"], "Wedding")[0]

        assert goal["utilized"] == 400

    def test_card_purchase_is_utilized_and_its_bill_handed_back(
        self, db_session, service
    ):
        """A card purchase draws the goal down and the bank bill leaves the pool alone."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_card_txn(db_session, last, -900, "Wedding", day=6)
        # The bank-side bill paying that card statement.
        _add_txn(db_session, last, -900, "Credit Cards", day=10)

        created = service.create(
            name="Wedding fund", target_amount=5000, priority=0, start_month=last
        )
        assert created[0]["funded"] == 1100
        assert service.get_free_cash()["liquid"] == 1100

        goal = service.set_spending_link(created[0]["id"], "Wedding")[0]

        assert goal["utilized"] == 900
        # The bill no longer shrinks the month's free cash — the goal paid it —
        # and the card purchase is not charged a second time on top of it.
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["liquid"] == 1100

    def test_explicit_link_on_a_card_purchase_is_utilized(self, db_session, service):
        """A card purchase linked by hand is spent from its goal, not ignored."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        purchase = _add_card_txn(db_session, last, -300, "Travel", day=6)

        created = service.create(
            name="Trip", target_amount=5000, priority=0, start_month=last
        )
        goals = service.link_transaction(
            goal_id=created[0]["id"],
            source_type="transaction",
            source_id=purchase.unique_id,
            source_table="credit_card_transactions",
            link_type=LINK_UTILIZATION,
        )

        assert goals[0]["utilized"] == 300

    def test_explicit_link_beats_the_project(self, db_session, service):
        """One transaction linked elsewhere by hand stays with that goal."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_txn(db_session, last, -500, "Wedding", day=6)
        other = _add_txn(db_session, last, -200, "Wedding", day=8)

        # Wedding fund fills at 1000, so Honeymoon holds the rest to pay with.
        created = service.create(
            name="Wedding fund", target_amount=1000, priority=0, start_month=last
        )
        created = service.create(
            name="Honeymoon", target_amount=5000, priority=1, start_month=last
        )
        ids = {g["name"]: g["id"] for g in created}
        service.set_spending_link(ids["Wedding fund"], "Wedding")
        service.link_transaction(
            goal_id=ids["Honeymoon"],
            source_type="transaction",
            source_id=other.unique_id,
            source_table="bank_transactions",
            link_type=LINK_UTILIZATION,
        )

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Wedding fund"]["utilized"] == 500
        assert goals["Honeymoon"]["utilized"] == 200

    def test_a_project_is_funded_by_one_goal_at_a_time(self, db_session, service):
        """Pointing a second goal at the project releases the first."""
        last = _month_str(1)
        _create_project(db_session, "Wedding")
        service.create(name="A", target_amount=1000, priority=0, start_month=last)
        created = service.create(
            name="B", target_amount=1000, priority=1, start_month=last
        )
        ids = {g["name"]: g["id"] for g in created}

        service.set_spending_link(ids["A"], "Wedding")
        goals = {g["name"]: g for g in service.set_spending_link(ids["B"], "Wedding")}

        assert goals["A"]["utilization_category"] is None
        assert goals["B"]["utilization_category"] == "Wedding"

    def test_unlinking_restores_the_spend_as_an_expense(self, db_session, service):
        """Passing ``None`` detaches the project."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        _create_project(db_session, "Wedding")
        _add_txn(db_session, last, -500, "Wedding", day=6)
        created = service.create(
            name="Wedding fund", target_amount=5000, priority=0, start_month=last
        )
        goal_id = created[0]["id"]
        service.set_spending_link(goal_id, "Wedding")

        goal = service.set_spending_link(goal_id, None)[0]

        assert goal["utilization_category"] is None
        assert goal["utilized"] == 0

    def test_tags_narrow_the_rule_like_a_yearly_envelope(self, db_session, service):
        """A category + tags link claims only the envelope's tags."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        CategoriesTagsService(db_session).add_category("Leisure", ["Vacation", "Movies"])
        _add_txn(db_session, last, -900, "Leisure", tag="Vacation", day=6)
        _add_txn(db_session, last, -80, "Leisure", tag="Movies", day=7)

        created = service.create(
            name="Trip", target_amount=5000, priority=0, start_month=last
        )
        goal = service.set_spending_link(created[0]["id"], "Leisure", ["Vacation"])[0]

        assert goal["utilization_category"] == "Leisure"
        assert goal["utilization_tags"] == "Vacation"
        assert goal["utilized"] == 900

    def test_all_tags_is_stored_as_the_whole_category(self, db_session, service):
        """``all_tags`` (a project's anchor rule) covers every tag."""
        _create_project(db_session, "Wedding")
        created = service.create(name="Goal", target_amount=1000, priority=0)
        goal = service.set_spending_link(created[0]["id"], "Wedding", ["all_tags"])[0]
        assert goal["utilization_tags"] is None

    def test_rule_set_from_the_goal_editor_applies(self, db_session, service):
        """The reverse direction: a goal naming its own category/tags."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        CategoriesTagsService(db_session).add_category("Leisure", ["Vacation"])
        _add_txn(db_session, last, -400, "Leisure", tag="Vacation", day=6)

        created = service.create(
            name="Trip",
            target_amount=5000,
            priority=0,
            start_month=last,
            utilization_category="Leisure",
            utilization_tags="Vacation",
        )

        assert created[0]["utilized"] == 400

    def test_higher_priority_goal_wins_an_overlapping_rule(self, db_session, service):
        """Two rules matching one row resolve by waterfall order."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=8000)
        CategoriesTagsService(db_session).add_category("Leisure", ["Vacation"])
        _add_txn(db_session, last, -400, "Leisure", tag="Vacation", day=6)

        service.create(
            name="First",
            target_amount=5000,
            priority=0,
            start_month=last,
            utilization_category="Leisure",
        )
        created = service.create(
            name="Second",
            target_amount=5000,
            priority=1,
            start_month=last,
            utilization_category="Leisure",
            utilization_tags="Vacation",
        )

        goals = {g["name"]: g for g in created}
        assert goals["First"]["utilized"] == 400
        assert goals["Second"]["utilized"] == 0


class TestRebuild:
    """Restating history is explicit, previewable, and respects closed goals."""

    def test_reorder_restates_history_under_the_new_order(self, db_session, service):
        """Reordering rebuilds the ledger — the list and its numbers agree at once."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)
        ids = {g["name"]: g["id"] for g in service.get_all()}

        returned = service.reorder([ids["Second"], ids["First"]])

        assert [g["name"] for g in returned] == ["Second", "First"]
        assert {g["name"]: g["funded"] for g in returned} == {"First": 0, "Second": 500}
        assert {g["name"]: g["funded"] for g in service.get_all()} == {
            "First": 0,
            "Second": 500,
        }

    def test_rebuild_dry_run_previews_without_writing(self, db_session, service):
        """A dry run reports the diff and leaves the ledger untouched.

        The priorities are swapped underneath the ledger (as an older,
        forward-only reorder left them), so the stored months still hold the
        old order's amounts.
        """
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.repo.set_priorities([ids["Second"], ids["First"]])

        preview = service.rebuild(dry_run=True)
        deltas = {c["name"]: c["delta"] for c in preview["changes"]}
        assert deltas["Second"] == 500
        assert deltas["First"] == -500

        unchanged = {g["name"]: g["funded"] for g in service.get_all()}
        assert unchanged == {"First": 500, "Second": 0}

    def test_rebuild_commits_the_new_order(self, db_session, service):
        """Committing the rebuild restates the months under the new priorities."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.repo.set_priorities([ids["Second"], ids["First"]])

        service.rebuild(dry_run=False)

        after = {g["name"]: g["funded"] for g in service.get_all()}
        assert after == {"First": 0, "Second": 500}

    def test_a_reorder_that_fails_midway_changes_nothing(
        self, db_session, service, monkeypatch
    ):
        """The new order, the deleted history and its rewrite commit together.

        Committed one by one, a failure — or a request reading in between —
        found the order changed and the history deleted but not rewritten. A
        write that dies halfway must leave the order and the ledger exactly
        as they were.
        """
        for offset in (2, 1):
            _seed_surplus(db_session, _month_str(offset), income=10000, expenses=9500)
        start = _month_str(2)
        service.create(name="First", target_amount=5000, priority=0, start_month=start)
        service.create(name="Second", target_amount=5000, priority=1, start_month=start)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        ledger_before = SavingsGoalService(db_session)._stored_allocations()
        assert ledger_before

        failing = SavingsGoalService(db_session)
        real_upsert = failing.repo.upsert_allocation
        calls = {"n": 0}

        def upsert_then_fail(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("disk full")
            return real_upsert(*args, **kwargs)

        monkeypatch.setattr(failing.repo, "upsert_allocation", upsert_then_fail)
        with pytest.raises(RuntimeError):
            failing.reorder([ids["Second"], ids["First"]])

        fresh = SavingsGoalService(db_session)
        assert fresh._stored_allocations() == ledger_before
        assert [g.name for g in fresh._goals_in_order()] == ["First", "Second"]

    def test_rebuild_cannot_take_money_out_of_a_closed_goal(
        self, db_session, service
    ):
        """A closed goal's allocations are frozen — a rebuild can't reclaim them."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        created = service.create(
            name="Done", target_amount=500, priority=1, start_month=last
        )
        service.create(name="Other", target_amount=5000, priority=0, start_month=last)
        done_id = next(g["id"] for g in created if g["name"] == "Done")

        # `Other` is above it, so `Done` only gets funded once it is alone.
        service.reorder([done_id, next(g["id"] for g in service.get_all() if g["name"] == "Other")])
        assert {g["name"]: g["funded"] for g in service.get_all()}["Done"] == 500

        service.close(done_id)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.reorder([ids["Other"], ids["Done"]])

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Done"]["funded"] == 500
        # The closed goal's 500 stays spoken for, so `Other` only sees the rest.
        assert goals["Other"]["funded"] == 0


class TestCostWithoutGoals:
    """A user who keeps no goals must not pay for the allocation machinery."""

    def test_month_view_short_circuits_before_scanning_transactions(
        self, db_session, service, monkeypatch
    ):
        """With no goals defined, the month view never loads transactions.

        The budget page renders this section for every month it shows, so the
        no-goals path has to be free. Scanning every transaction there once
        made the budget page's post-mutation refresh miss its deadline.
        """
        calls = []
        monkeypatch.setattr(
            service, "_compute_context", lambda: calls.append(1) or {}
        )

        result = service.get_month_allocations(2026, 6)

        assert calls == []
        assert result["goals"] == []
        assert result["total_allocated"] == 0.0

    def test_context_is_computed_once_per_request(self, db_session, service):
        """The transaction scan is memoised across one service instance.

        A single request needs the context twice — once to allocate, once to
        enrich — and the scan is the expensive part of both.
        """
        _seed_surplus(db_session, _month_str(1), income=10000, expenses=9000)
        service.create(name="Goal", target_amount=5000, start_month=_month_str(1))

        calls = []
        original = service._compute_context
        service._compute_context = lambda: calls.append(1) or original()
        service._context_cache = None

        service.get_all()

        assert len(calls) == 1


class TestFreeCashPool:
    """The unearmarked pool absorbs a deficit before any goal is touched."""

    def test_unallocated_surplus_lands_in_the_pool(self, db_session, service):
        """Money no goal claimed stays free rather than vanishing."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)

        service.create(name="Goal", target_amount=1000, priority=0, start_month=last)

        pool = service.get_free_cash()
        assert pool["has_goals"] is True
        # 3000 surplus, 1000 earmarked by the goal, 2000 left free.
        assert pool["free_cash"] == 2000
        assert pool["earmarked"] == 1000
        assert pool["liquid"] == 3000

    def test_pool_absorbs_the_whole_deficit(self, db_session, service):
        """A deficit smaller than the pool never reaches the goals."""
        good, bad = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 20000)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        goal = service.get_all()[0]
        assert goal["funded"] == 5000
        assert goal["clawed_back"] == 0
        # 20000 opening + 1000, less the 5000 that filled the goal, - 3000.
        assert service.get_free_cash()["free_cash"] == 13000

    def test_goals_absorb_only_what_the_pool_could_not(self, db_session, service):
        """Once the pool is dry the remainder comes out of the goals."""
        good, bad = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 500)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        goal = service.get_all()[0]
        # The 500 opening and the 1000 surplus both went to the goal; the 3000
        # deficit takes those 1500 back and the pool ends 1500 below zero
        # rather than hiding it.
        assert goal["clawed_back"] == 1500
        assert goal["funded"] == 0
        assert service.get_free_cash()["free_cash"] == -1500

    def test_clawback_runs_in_reverse_priority(self, db_session, service):
        """The least important goal is drained first — the waterfall in reverse."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=8000)
        _seed_surplus(db_session, bad, income=5000, expenses=5600)

        service.create(name="First", target_amount=1000, priority=0, start_month=good)
        service.create(name="Second", target_amount=1000, priority=1, start_month=good)

        goals = {g["name"]: g for g in service.get_all()}
        # Both filled from the 2000 surplus; the 600 deficit takes from Second.
        assert goals["Second"]["clawed_back"] == 600
        assert goals["First"]["clawed_back"] == 0
        assert goals["First"]["funded"] == 1000
        assert goals["Second"]["funded"] == 400

    def test_clawback_stops_at_what_the_goal_already_spent(self, db_session, service):
        """Money utilized out of a goal is gone and can never be reclaimed."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=6000)
        spend = _add_txn(db_session, good, -700, "Travel", day=20)

        goals = service.create(
            name="Goal", target_amount=5000, priority=0, start_month=good
        )
        service.link_transaction(
            goals[0]["id"], "transaction", spend.unique_id,
            "bank_transactions", LINK_UTILIZATION,
        )
        # The link arrived after the ledger was written, and history is never
        # silently restated — an explicit rebuild is what applies it.
        service.rebuild()

        goal = service.get_all()[0]
        # The utilization leaves the good month's surplus at 1000, of which
        # 700 is already spent. The 1000 deficit can only reclaim the 300
        # still available.
        assert goal["utilized"] == 700
        assert goal["clawed_back"] == 300
        assert goal["available"] == 0
        assert goal["funded"] == 700

    def test_closed_goal_is_never_clawed_back(self, db_session, service):
        """A frozen goal's allocations survive a later deficit month untouched."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)

        created = service.create(
            name="Goal", target_amount=5000, priority=0, start_month=good
        )
        service.close(created[0]["id"])
        # The deficit only lands once the goal is already frozen.
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        goal = service.get_all()[0]
        assert goal["is_closed"] is True
        assert goal["clawed_back"] == 0
        assert goal["funded"] == 1000

    def test_pool_reports_nothing_when_no_goals_exist(self, db_session, service):
        """With no goals the pool means nothing, and costs no transaction scan."""
        _seed_surplus(db_session, _month_str(1), income=10000, expenses=7000)

        assert service.get_free_cash() == {
            "free_cash": 0.0,
            "earmarked": 0.0,
            "liquid": 0.0,
            "clawed_back_this_month": 0.0,
            "has_goals": False,
        }

    def test_month_view_reports_the_clawback(self, db_session, service):
        """The budget month view explains where a deficit month's money went."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        year, month = (int(part) for part in bad.split("-"))
        view = service.get_month_allocations(year, month)
        assert view["clawed_back"] == 1000
        # The 3000 overspend took the goal's 1000; the other 2000 was spent
        # from money no goal held, and the pool shows it.
        assert view["free_cash"] == -2000
        assert view["goals"][0]["allocated"] == -1000

    def test_deleting_the_earliest_goal_releases_its_earmark(self, db_session, service):
        """Deleting a goal hands exactly its earmark back to the pool.

        The history before the goals dips below zero. That hole is carried, not
        floored, so it never depends on which goal starts first: deleting the
        earliest goal cannot move it and quietly destroy free cash.
        """
        overspent, early, middle, late = (_month_str(n) for n in (4, 3, 2, 1))
        _seed_free_cash(db_session, 1000)
        _seed_surplus(db_session, overspent, income=1000, expenses=6000)
        for month in (early, middle, late):
            _seed_surplus(db_session, month, income=10000, expenses=7000)

        service.create(name="Early", target_amount=3000, priority=0, start_month=early)
        service.create(name="Late", target_amount=1000, priority=1, start_month=late)
        before = service.get_free_cash()
        early_id = next(g["id"] for g in service.get_all() if g["name"] == "Early")

        service.delete(early_id)
        after = service.get_free_cash()

        # 1000 - 5000 + 3 x 3000 = 5000 of real money, 4000 of it earmarked.
        assert before["free_cash"] == 1000
        assert after["free_cash"] == before["free_cash"] + 3000
        assert after["liquid"] == before["liquid"]

    def test_a_drained_pool_reports_positive_zero(self, db_session, service):
        """A pool drained to nothing reads 0.0, never the -0.0 rounding leaves."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=4000)
        _seed_surplus(db_session, _month_str(0), income=1000, expenses=2000)
        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        pools = [row["free_cash"] for row in service.get_timeline(months=None)["months"]]
        assert 0.0 in pools
        assert all(math.copysign(1.0, pool) == 1.0 for pool in pools if pool == 0)


class TestFreeCashBefore:
    """The money already in the accounts when a goal started, offered as its opening balance.

    Goals only draw on each month's new surplus, so that money otherwise sits
    in the free-cash pool for good.
    """

    def test_earliest_goal_sees_prior_wealth_and_earlier_surplus(
        self, db_session, service
    ):
        """Before any goal starts, the pool is prior wealth walked through history."""
        before, start = _month_str(3), _month_str(2)
        _seed_free_cash(db_session, 5000)
        _seed_surplus(db_session, before, income=10000, expenses=9000)
        _seed_surplus(db_session, start, income=10000, expenses=7000)
        goal_id = service.create(
            name="Goal", target_amount=50000, start_month=start
        )[0]["id"]

        assert service.get_free_cash_before(start, goal_id)["free_cash"] == 6000

    def test_the_goals_own_opening_balance_does_not_count(self, db_session, service):
        """Asking twice gives the same answer — the goal is left out of its own figure."""
        start = _month_str(2)
        _seed_free_cash(db_session, 5000)
        goal_id = service.create(
            name="Goal", target_amount=50000, opening_balance=5000, start_month=start
        )[0]["id"]

        assert service.get_free_cash_before(start, goal_id)["free_cash"] == 5000

    def test_later_goal_sees_what_earlier_goals_left(self, db_session, service):
        """A goal starting after another sees the pool that goal's cap left behind."""
        early, late = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 1000)
        _seed_surplus(db_session, early, income=10000, expenses=7000)
        service.create(
            name="Early", target_amount=50000, monthly_cap=1000, priority=0,
            start_month=early,
        )

        assert service.get_free_cash_before(late)["free_cash"] == 3000

    def test_claiming_it_empties_the_pool_without_moving_liquid(
        self, db_session, service
    ):
        """Taking the figure as the opening balance and restating earmarks all of it.

        This is the dashboard case: a flat pool that goals never touched, then
        a deficit month drains it before reaching any goal. Once claimed, the
        same deficit comes out of the goal instead, and the total liquid money
        the goals sit over is unchanged.
        """
        start, bad = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 5000)
        _seed_surplus(db_session, start, income=10000, expenses=7000)
        _seed_surplus(db_session, bad, income=5000, expenses=9000)
        goal_id = service.create(
            name="Goal", target_amount=50000, start_month=start
        )[0]["id"]
        before = service.get_free_cash()
        assert before["free_cash"] == 0

        claim = service.get_free_cash_before(start, goal_id)["free_cash"]
        service.update(goal_id, opening_balance=claim)
        service.rebuild(from_month=start)

        after = service.get_free_cash()
        goal = service.get_all()[0]
        assert after["free_cash"] == 0
        assert after["liquid"] == before["liquid"]
        assert goal["clawed_back"] == 4000
        assert goal["funded"] == 5000 + 3000 - 4000

    def test_an_opening_balance_leaves_the_pool_when_its_goal_starts(
        self, db_session, service
    ):
        """A later goal's opening balance cannot make an earlier deficit claw back.

        It used to leave the pool when the *earliest* goal started, so the
        pool looked empty months before that money was actually earmarked and
        the deficit in between was taken out of the earlier goal instead.
        """
        early, deficit, late = _month_str(3), _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 5000)
        _seed_surplus(db_session, early, income=10000, expenses=8000)
        _seed_surplus(db_session, deficit, income=5000, expenses=9000)
        # Early fills at 2000, so the rest of the pool stays free for the deficit.
        service.create(name="Early", target_amount=2000, priority=0, start_month=early)
        service.create(
            name="Late", target_amount=10000, opening_balance=3000, priority=1,
            start_month=late,
        )

        goal = next(g for g in service.get_all() if g["name"] == "Early")
        assert goal["clawed_back"] == 0
        assert goal["funded"] == 2000

    def test_claiming_does_not_move_the_figure_it_claimed(self, db_session, service):
        """With an earlier goal in place, the figure is the same before and after a claim."""
        early, deficit, start = _month_str(4), _month_str(3), _month_str(2)
        _seed_free_cash(db_session, 5000)
        _seed_surplus(db_session, deficit, income=5000, expenses=9000)
        service.create(
            name="Early", target_amount=10000, opening_balance=500, priority=0,
            start_month=early,
        )
        goal_id = next(
            g["id"]
            for g in service.create(
                name="Claim", target_amount=50000, priority=1, start_month=start
            )
            if g["name"] == "Claim"
        )

        claim = service.get_free_cash_before(start, goal_id)["free_cash"]
        service.update(goal_id, opening_balance=claim)
        service.rebuild(from_month=start)

        assert claim == 0
        assert service.get_free_cash_before(start, goal_id)["free_cash"] == claim
        early_goal = next(g for g in service.get_all() if g["name"] == "Early")
        assert early_goal["clawed_back"] == 4000

    def test_rejects_a_malformed_month(self, service):
        """An unparseable month is a validation error, not a silent zero."""
        with pytest.raises(ValidationException):
            service.get_free_cash_before("not-a-month")


@contextmanager
def _commit_counter():
    """Yield a list that gains an entry for every commit inside the block."""
    commits: list[int] = []

    def record(_session):
        commits.append(1)

    event.listen(Session, "after_commit", record)
    try:
        yield commits
    finally:
        event.remove(Session, "after_commit", record)


class TestPersistenceIsIdempotent:
    """`ensure_allocations` runs from read paths, so it must not write on every GET.

    Rewriting the open month with the number it already held made a single
    dashboard load commit six times over: a SQLite write lock per read, a
    churned database file, and — since a commit invalidates the cross-request
    caches in ``backend/utils/data_cache.py`` — those caches being discarded
    on exactly the load that needed them most.

    These use the *current* month: it is the only one `ensure_allocations`
    recomputes (closed months on record are left alone), so it is the row
    that used to be rewritten on every read.
    """

    def test_first_read_persists_the_ledger(self, db_session, service):
        """The allocations still land the first time they are computed."""
        this_month = _month_str(0)
        _seed_surplus(db_session, this_month, income=10000, expenses=7000)
        service.create(name="Vacation", target_amount=1000, start_month=this_month)

        service.get_all()

        assert not service.repo.get_allocations().empty

    def test_repeat_reads_write_nothing(self, db_session, service):
        """Once the ledger agrees with the simulation, reads stop committing."""
        this_month = _month_str(0)
        _seed_surplus(db_session, this_month, income=10000, expenses=7000)
        service.create(name="Vacation", target_amount=1000, start_month=this_month)
        service.get_all()

        with _commit_counter() as commits:
            service.get_all()
            service.get_all()

        assert commits == []

    def test_a_disagreeing_ledger_row_is_rewritten(self, db_session, service):
        """Skipping no-op writes must not skip the writes that matter."""
        this_month = _month_str(0)
        _seed_surplus(db_session, this_month, income=10000, expenses=7000)
        service.create(name="Vacation", target_amount=1000, start_month=this_month)
        service.get_all()

        stored = service.repo.get_allocations().iloc[0]
        expected = float(stored["amount"])
        service.repo.upsert_allocation(
            int(stored["goal_id"]),
            int(stored["year"]),
            int(stored["month"]),
            expected + 500.0,
            "auto",
        )

        with _commit_counter() as commits:
            service.get_all()

        assert commits  # the tampered row was corrected
        rows = service.repo.get_allocations()
        corrected = rows[
            (rows["goal_id"] == int(stored["goal_id"]))
            & (rows["year"] == int(stored["year"]))
            & (rows["month"] == int(stored["month"]))
        ]
        assert float(corrected["amount"].iloc[0]) == pytest.approx(expected)


class TestTimeline:
    """The ledger read month by month: allocations, clawbacks and the pool."""

    def test_every_month_from_the_first_goal_is_present(self, db_session, service):
        """Months where nothing moved still get a row — a gap would read as skipped."""
        start = _month_str(3)
        _seed_surplus(db_session, start, income=10000, expenses=7000)

        service.create(name="Vacation", target_amount=1000, start_month=start)

        timeline = service.get_timeline()
        months = [row["month"] for row in timeline["months"]]
        assert months == [_month_str(n) for n in (3, 2, 1, 0)]
        assert timeline["total_months"] == 4
        assert timeline["months"][-1]["is_provisional"] is True

    def test_each_month_reports_what_every_goal_took(self, db_session, service):
        """Per-goal rows carry the month's allocation, keyed by goal id."""
        start = _month_str(1)
        _seed_surplus(db_session, start, income=10000, expenses=7000)

        service.create(
            name="First", target_amount=5000, priority=0, monthly_cap=1000,
            start_month=start,
        )
        service.create(
            name="Second", target_amount=5000, priority=1, monthly_cap=500,
            start_month=start,
        )

        month = service.get_timeline()["months"][0]
        amounts = {row["name"]: row["total"] for row in month["goals"]}
        assert amounts == {"First": 1000, "Second": 500}
        assert month["allocated"] == 1500
        assert month["surplus"] == 3000

    def test_free_cash_is_reported_per_month(self, db_session, service):
        """What the goals left behind is on every row, not just today's."""
        first, second = _month_str(2), _month_str(1)
        _seed_surplus(db_session, first, income=10000, expenses=7000)
        _seed_surplus(db_session, second, income=10000, expenses=9000)

        service.create(name="Goal", target_amount=2000, monthly_cap=1000, start_month=first)

        by_month = {row["month"]: row for row in service.get_timeline()["months"]}
        # 3000 surplus less the 1000 the goal took, then 1000 more surplus
        # less its second 1000.
        assert by_month[first]["free_cash"] == 2000
        assert by_month[second]["free_cash"] == 2000

    def test_a_deficit_month_reports_its_clawback_apart_from_funding(
        self, db_session, service
    ):
        """Funding and clawback are separate figures — netting hides half the month."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, start_month=good)

        by_month = {row["month"]: row for row in service.get_timeline()["months"]}
        assert by_month[good]["allocated"] == 1000
        assert by_month[bad]["clawed_back"] == 1000
        assert by_month[bad]["allocated"] == 0
        assert by_month[bad]["free_cash"] == -2000

    def test_window_trims_to_the_trailing_months_it_was_asked_for(
        self, db_session, service
    ):
        """`months` bounds the window while `total_months` keeps offering "all time"."""
        start = _month_str(5)
        _seed_surplus(db_session, start, income=10000, expenses=7000)
        service.create(name="Goal", target_amount=1000, start_month=start)

        trimmed = service.get_timeline(months=2)
        assert [row["month"] for row in trimmed["months"]] == [
            _month_str(1),
            _month_str(0),
        ]
        assert trimmed["total_months"] == 6
        assert len(service.get_timeline(months=None)["months"]) == 6

    def test_no_goals_costs_no_transaction_scan(self, db_session, service):
        """With no goals there is no timeline, and nothing is read to prove it."""
        calls = []
        original = service.transactions_service.get_data_for_analysis
        service.transactions_service.get_data_for_analysis = lambda *a, **k: (
            calls.append(1) or original(*a, **k)
        )

        timeline = service.get_timeline()

        assert timeline == {
            "has_goals": False,
            "total_months": 0,
            "months": [],
            "goals": [],
        }
        assert calls == []


def _create_investment_goal(service, **overrides):
    """Create an investment goal over Investments / Pakam and return its payload."""
    fields = {
        "name": "Invest",
        "target_amount": 100000,
        "kind": "investment",
        "contribution_category": "Investments",
        "contribution_tags": "Pakam",
        **overrides,
    }
    created = service.create(**fields)
    return next(g for g in created if g["name"] == fields["name"])


class TestInvestmentGoals:
    """An investment goal is filled by the money actually moved into investments."""

    def test_progress_is_the_net_invested_from_its_start_month(
        self, db_session, service
    ):
        """Deposits add, withdrawals take back, and earlier transfers don't count."""
        before, first, second = _month_str(3), _month_str(2), _month_str(1)
        _add_txn(db_session, before, -9000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, first, -30000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, second, -20000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, second, 5000, "Investments", tag="Pakam", day=20)
        _add_txn(db_session, second, -7000, "Investments", tag="Stocks", day=4)

        goal = _create_investment_goal(service, start_month=first)

        assert goal["kind"] == "investment"
        assert goal["contributed"] == 45000
        assert goal["funded"] == 45000
        assert goal["allocated"] == 0
        assert goal["progress_pct"] == 45.0

    def test_it_takes_its_waterfall_turn_as_cash_to_invest(self, db_session, service):
        """Surplus fills an investment goal in priority order, waiting to be invested."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)

        _create_investment_goal(service, priority=0, start_month=last)
        service.create(name="Trip", target_amount=5000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Invest"]["funded"] == 3000
        assert goals["Invest"]["to_invest"] == 3000
        assert goals["Trip"]["funded"] == 0

    def test_investing_is_not_overspending(self, db_session, service):
        """A transfer bigger than the pool never takes money back from a cash goal."""
        good, big = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=7000)
        _seed_surplus(db_session, big, income=10000, expenses=10000)
        _add_txn(db_session, big, -50000, "Investments", tag="Pakam", day=3)

        service.create(name="Trip", target_amount=2000, priority=0, start_month=good)
        _create_investment_goal(service, priority=1, start_month=good)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Trip"]["funded"] == 2000
        assert goals["Trip"]["clawed_back"] == 0
        assert goals["Invest"]["funded"] == 50000
        pool = service.get_free_cash()
        # Invest held the 1000 Trip left; the other 49000 of the transfer came
        # from money no goal held, so the pool shows it below zero.
        assert pool["free_cash"] == -49000
        # The invested money is not cash, so it is neither earmarked nor liquid.
        assert pool["earmarked"] == 2000
        assert pool["liquid"] == -47000

    def test_the_same_transfer_as_a_plain_expense_does_claw_back(
        self, db_session, service
    ):
        """Without the investment goal the transfer is a deficit, as before."""
        good, big = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=7000)
        _seed_surplus(db_session, big, income=10000, expenses=10000)
        _add_txn(db_session, big, -50000, "Investments", tag="Pakam", day=3)

        service.create(name="Trip", target_amount=2000, priority=0, start_month=good)

        assert service.get_all()[0]["clawed_back"] == 2000

    def test_a_withdrawal_goes_back_into_its_cash(self, db_session, service):
        """Money taken back out of the investment is still the goal's, as cash."""
        first, second = _month_str(2), _month_str(1)
        _seed_surplus(db_session, first, income=10000, expenses=0)
        _add_txn(db_session, first, -10000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, second, 4000, "Investments", tag="Pakam", day=3)

        goal = _create_investment_goal(service, start_month=first)

        assert goal["funded"] == 10000
        assert goal["to_invest"] == 4000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["earmarked"] == 4000

    def test_a_withdrawal_it_never_invested_returns_to_the_pool(
        self, db_session, service
    ):
        """Taking out money invested before the goal existed frees it.

        It lands in free cash, which the waterfall then hands to the goal like
        any other free money — not as its own withdrawal.
        """
        before, start = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 10000)
        _add_txn(db_session, before, -10000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, start, 4000, "Investments", tag="Pakam", day=3)

        goal = _create_investment_goal(service, start_month=start)

        assert goal["funded"] == 4000
        assert goal["contributed"] == 0
        assert goal["allocated"] == 4000
        assert service.get_free_cash()["free_cash"] == 0

    def test_this_month_shows_the_months_net_transfers(self, db_session, service):
        """The row's "this month" figure is what moved this month."""
        now = _month_str(0)
        _add_txn(db_session, now, -3000, "Investments", tag="Pakam", day=1)

        goal = _create_investment_goal(service, start_month=now)

        assert goal["this_month_allocation"] == 3000

    def test_cash_only_settings_are_refused(self, db_session, service):
        """An investment goal takes no cash-goal settings."""
        with pytest.raises(ValidationException):
            _create_investment_goal(service, name="Capped", monthly_cap=500)
        with pytest.raises(ValidationException):
            _create_investment_goal(service, name="Opening", opening_balance=500)

        goal = _create_investment_goal(service)
        with pytest.raises(ValidationException):
            service.set_spending_link(goal["id"], "Leisure")
        with pytest.raises(ValidationException):
            service.link_transaction(
                goal_id=goal["id"],
                source_type="transaction",
                source_id=1,
                source_table="bank_transactions",
                link_type=LINK_CONTRIBUTION,
            )

    def test_it_always_counts_the_investments_category(self, db_session, service):
        """No category to pick: every investment transfer counts unless tags narrow it."""
        month = _month_str(1)
        _add_txn(db_session, month, -4000, "Investments", tag="Pakam", day=3)
        _add_txn(db_session, month, -1500, "Investments", tag="Stocks", day=4)
        _add_txn(db_session, month, -900, "Savings", tag="Pakam", day=5)

        created = service.create(
            name="All", target_amount=10000, kind="investment", start_month=month
        )
        every = next(g for g in created if g["name"] == "All")
        assert every["contribution_category"] == "Investments"
        assert every["funded"] == 5500
        # Two goals matching one transfer would share it; keep this one alone.
        service.delete(every["id"])

        created = service.create(
            name="Pakam only",
            target_amount=10000,
            kind="investment",
            start_month=month,
            contribution_category="Savings",
            contribution_tags="Pakam",
        )
        narrowed = next(g for g in created if g["name"] == "Pakam only")
        # A category sent anyway is ignored; the tag still narrows it.
        assert narrowed["contribution_category"] == "Investments"
        assert narrowed["funded"] == 4000

    def test_its_category_cannot_be_changed(self, db_session, service):
        """An update naming another category leaves the goal on Investments."""
        goal = _create_investment_goal(service)

        updated = service.update(goal["id"], contribution_category="Savings")

        assert next(g for g in updated if g["id"] == goal["id"])["contribution_category"] == "Investments"

    def test_goals_without_a_kind_are_cash_goals(self, db_session, service):
        """Rows older than the column read as cash goals."""
        created = service.create(name="Old", target_amount=1000)
        goal_id = created[0]["id"]
        service.repo.update(goal_id, kind=None)

        assert service.get_all()[0]["kind"] == "cash"

    def test_creating_and_deleting_it_restate_the_past(self, db_session, service):
        """Past clawbacks follow whether the transfers belong to a goal."""
        good, big = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=7000)
        _seed_surplus(db_session, big, income=10000, expenses=10000)
        _add_txn(db_session, big, -50000, "Investments", tag="Pakam", day=3)
        service.create(name="Trip", target_amount=2000, priority=0, start_month=good)
        assert service.get_all()[0]["clawed_back"] == 2000

        goal = _create_investment_goal(service, priority=1, start_month=good)
        assert {g["name"]: g for g in service.get_all()}["Trip"]["clawed_back"] == 0

        service.delete(goal["id"])
        assert service.get_all()[0]["clawed_back"] == 2000


class TestRuleFundedGoals:
    """A goal with its own income on the way borrows until the income lands."""

    def _wedding(self, service, start, target=10000, **overrides):
        """Create a goal saved into by Other Income / Wedding, spent from Wedding."""
        created = service.create(
            name="Wedding",
            target_amount=target,
            priority=0,
            start_month=start,
            contribution_category="Other Income",
            contribution_tags="Wedding",
            utilization_category="Wedding",
            **overrides,
        )
        return next(g for g in created if g["name"] == "Wedding")

    def test_its_income_displaces_the_surplus_that_filled_it(self, db_session, service):
        """Surplus fills it until its gifts land; then the gifts come first.

        The surplus the gifts make unnecessary goes back to free cash, so a
        goal whose income covers its target ends up holding that income alone.
        """
        before, gifts = _month_str(2), _month_str(1)
        _seed_surplus(db_session, before, income=10000, expenses=6000)
        _seed_surplus(db_session, gifts, income=10000, expenses=10000)
        _add_txn(db_session, gifts, 12000, "Other Income", tag="Wedding", day=6)

        self._wedding(service, before)

        goal = service.get_all()[0]
        assert goal["allocated"] == 0
        # 12000 of gifts against a 10000 target: it keeps 10000 and the rest
        # spills into the month's surplus.
        assert goal["contributed"] == 10000
        assert goal["funded"] == 10000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 6000  # 4000 of salary surplus + 2000 spilled
        assert pool["liquid"] == 16000

    def test_surplus_tops_up_income_short_of_the_target(self, db_session, service):
        """Free cash fills what its income leaves short, in waterfall order."""
        before, gifts = _month_str(2), _month_str(1)
        _seed_surplus(db_session, before, income=10000, expenses=6000)
        _add_txn(db_session, gifts, 3000, "Other Income", tag="Wedding", day=6)

        self._wedding(service, before)

        goal = service.get_all()[0]
        assert goal["allocated"] == 4000
        assert goal["contributed"] == 3000
        assert goal["funded"] == 7000
        assert service.get_free_cash()["free_cash"] == 0

    def test_a_deficit_never_takes_its_income_back(self, db_session, service):
        """Overspending that ate into the gifts shows as negative free cash."""
        gifts, spent = _month_str(2), _month_str(1)
        _add_txn(db_session, gifts, 10000, "Other Income", tag="Wedding", day=6)
        _seed_surplus(db_session, spent, income=0, expenses=6000)

        self._wedding(service, gifts)

        goal = service.get_all()[0]
        assert goal["funded"] == 10000
        assert goal["clawed_back"] == 0
        pool = service.get_free_cash()
        # The 6000 was paid with the gifts; they are spoken for, so the pool
        # owes it rather than pretending the money is still there.
        assert pool["free_cash"] == -6000
        assert pool["liquid"] == 4000

    def test_an_overspend_past_the_income_held_shows_in_full(
        self, db_session, service
    ):
        """The pool shows the whole overspend, even past what the income goals hold."""
        gifts, spent = _month_str(2), _month_str(1)
        _add_txn(db_session, gifts, 10000, "Other Income", tag="Wedding", day=6)
        _seed_surplus(db_session, spent, income=0, expenses=15000)

        self._wedding(service, gifts)

        assert service.get_free_cash()["free_cash"] == -15000

    def test_a_later_surplus_refills_the_hole_before_any_goal(
        self, db_session, service
    ):
        """A negative pool is repaid first; only the rest of a surplus funds goals."""
        bad, good = _month_str(2), _month_str(1)
        _seed_surplus(db_session, bad, income=0, expenses=3000)
        _seed_surplus(db_session, good, income=5000, expenses=0)

        service.create(name="Trip", target_amount=10000, start_month=bad)

        goal = service.get_all()[0]
        assert goal["funded"] == 2000
        assert goal["clawed_back"] == 0
        assert service.get_free_cash()["free_cash"] == 0

    def test_a_carried_hole_never_claws_back_again(self, db_session, service):
        """Last month's overspend is settled; a quiet month takes nothing more."""
        funded, bad, quiet = _month_str(3), _month_str(2), _month_str(1)
        _seed_surplus(db_session, funded, income=4000, expenses=0)
        _seed_surplus(db_session, bad, income=0, expenses=6000)
        _seed_surplus(db_session, quiet, income=1000, expenses=1000)

        service.create(name="Trip", target_amount=10000, start_month=funded)

        goal = service.get_all()[0]
        assert goal["clawed_back"] == 4000
        assert goal["funded"] == 0
        assert service.get_free_cash()["free_cash"] == -2000

    def test_a_plain_goal_is_still_clawed_back_first(self, db_session, service):
        """Ordinary earmarks give money back before the pool goes negative."""
        good, gifts, spent = _month_str(3), _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=8000)
        _add_txn(db_session, gifts, 10000, "Other Income", tag="Wedding", day=6)
        _seed_surplus(db_session, spent, income=0, expenses=5000)

        service.create(name="Trip", target_amount=2000, priority=0, start_month=good)
        self._wedding(service, good)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Trip"]["clawed_back"] == 2000
        assert goals["Wedding"]["clawed_back"] == 0
        assert service.get_free_cash()["free_cash"] == -3000

    def test_a_bill_before_the_income_is_fronted_from_free_cash_and_repaid(
        self, db_session, service
    ):
        """Spending the goal cannot yet cover is borrowed and repaid by the gifts."""
        bill, gifts = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 20000)
        _seed_surplus(db_session, bill, income=5000, expenses=5000)
        _add_txn(db_session, bill, -8000, "Wedding", tag="Venue", day=9)
        _seed_surplus(db_session, gifts, income=5000, expenses=5000)
        _add_txn(db_session, gifts, 15000, "Other Income", tag="Wedding", day=6)

        self._wedding(service, bill)

        goal = service.get_all()[0]
        assert goal["fronted"] == 8000
        assert goal["utilized"] == 8000
        assert goal["contributed"] == 10000
        assert goal["released"] == 8000
        # It holds the gifts it kept less the bill: 10000 - 8000.
        assert goal["available"] == 2000
        pool = service.get_free_cash()
        # 20000 opening - 8000 fronted + 8000 repaid + 5000 of gifts spilled.
        assert pool["free_cash"] == 25000
        assert pool["liquid"] == 27000

    def test_a_goal_without_income_of_its_own_never_fronts(self, db_session, service):
        """A plain goal pays only with what it holds; the rest stays with free cash."""
        bill = _month_str(1)
        _seed_free_cash(db_session, 20000)
        _seed_surplus(db_session, bill, income=5000, expenses=5000)
        _add_txn(db_session, bill, -8000, "Wedding", tag="Venue", day=9)

        created = service.create(
            name="Plain",
            target_amount=10000,
            priority=0,
            start_month=bill,
            utilization_category="Wedding",
        )
        goal = next(g for g in created if g["name"] == "Plain")

        assert goal["fronted"] == 0
        assert goal["utilized"] == 8000
        assert goal["available"] == 2000
        assert service.get_free_cash()["free_cash"] == 10000

    def test_the_timeline_bar_is_its_income_not_what_the_income_repaid(
        self, db_session, service
    ):
        """A gift month reads as the whole gift, with the repaid bills apart."""
        bill, gifts = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 20000)
        _add_txn(db_session, bill, -8000, "Wedding", tag="Venue", day=9)
        _add_txn(db_session, gifts, 15000, "Other Income", tag="Wedding", day=6)

        self._wedding(service, bill, target=20000)

        months = {m["month"]: m for m in service.get_timeline(months=0)["months"]}
        paid = next(g for g in months[bill]["goals"] if g["name"] == "Wedding")
        given = next(g for g in months[gifts]["goals"] if g["name"] == "Wedding")
        assert paid["total"] == 5000
        assert paid["bridged"] == 3000
        assert given["total"] == 15000
        assert given["bridged"] == -3000

    def test_bills_beyond_its_income_are_owed_not_funded(self, db_session, service):
        """Progress is what it received; the unrepaid gap is reported as owed.

        With no free cash for the waterfall to top it up from, the 2000 of the
        bill its gifts never covered stays owed rather than counted as funding.
        """
        bill, gifts = _month_str(2), _month_str(1)
        _add_txn(db_session, bill, -12000, "Wedding", tag="Venue", day=9)
        _add_txn(db_session, gifts, 10000, "Other Income", tag="Wedding", day=6)

        self._wedding(service, bill, target=12000)

        goal = service.get_all()[0]
        # It received the 10000 of gifts; the other 2000 of the bill was paid
        # with free cash it never got back. The card must agree with its bars.
        assert goal["funded"] == 10000
        assert goal["owed"] == 2000
        assert goal["utilized"] == 12000
        assert goal["available"] == 0
        assert goal["progress_pct"] == 83.3
        assert goal["is_achieved"] is False
        bars = sum(
            g["total"]
            for m in service.get_timeline(months=0)["months"]
            for g in m["goals"]
            if g["name"] == "Wedding"
        )
        assert bars == goal["funded"]


class TestInvestmentGoalFunding:
    """An investment goal can name the income its transfers are paid from."""

    def _invest(self, service, start, **overrides):
        """Create an investment goal paid for by Other Income / Kickstart."""
        fields = {
            "name": "Invest",
            "target_amount": 200000,
            "kind": "investment",
            "start_month": start,
            "funding_category": "Other Income",
            "funding_tags": "Kickstart",
            **overrides,
        }
        created = service.create(**fields)
        return next(g for g in created if g["name"] == "Invest")

    def test_its_income_pays_for_the_transfers_before_free_cash(
        self, db_session, service
    ):
        """A transfer bigger than the income takes only the rest from free cash.

        The goal holds exactly what its income paid for; the rest is an
        ordinary transfer out of free cash.
        """
        month = _month_str(1)
        _seed_free_cash(db_session, 50000)
        _add_txn(db_session, month, 100000, "Other Income", tag="Kickstart", day=2)
        _add_txn(db_session, month, -123500, "Investments", tag="Pakam", day=5)

        goal = self._invest(service, month)

        # Its 100000 of income, topped up from the 50000 of free cash its
        # income does not cover; the transfer is paid from what it holds.
        assert goal["funded"] == 150000
        assert goal["to_invest"] == 26500
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["liquid"] == 26500

    def test_income_not_yet_invested_waits_as_earmarked_cash(self, db_session, service):
        """Unspent funding income is cash the goal holds, not free cash."""
        month = _month_str(1)
        _seed_free_cash(db_session, 50000)
        _add_txn(db_session, month, 30000, "Other Income", tag="Kickstart", day=2)
        _add_txn(db_session, month, -10000, "Investments", tag="Pakam", day=5)

        goal = self._invest(service, month)

        # Progress is what the goal holds, invested or not.
        assert goal["funded"] == 80000
        assert goal["to_invest"] == 70000
        pool = service.get_free_cash()
        assert pool["free_cash"] == 0
        assert pool["earmarked"] == 70000
        assert pool["liquid"] == 70000

    def test_income_before_its_start_month_is_ordinary_surplus(
        self, db_session, service
    ):
        """Only income from the goal's start month on is its own income.

        Earlier income is ordinary free cash — which the waterfall then hands
        to the goal as surplus, not as its income.
        """
        before, start = _month_str(2), _month_str(1)
        _add_txn(db_session, before, 30000, "Other Income", tag="Kickstart", day=2)

        goal = self._invest(service, start)

        assert goal["contributed"] == 0
        assert goal["allocated"] == 30000
        assert goal["to_invest"] == 30000
        assert service.get_free_cash()["free_cash"] == 0

    def test_its_progress_is_the_income_it_holds_invested_or_not(
        self, db_session, service
    ):
        """Investing only moves the goal's cash; transfers before it held any are not its."""
        early, late = _month_str(3), _month_str(1)
        _add_txn(db_session, early, -8000, "Investments", tag="Pakam", day=5)
        _add_txn(db_session, _month_str(2), 3000, "Investments", tag="Pakam", day=5)
        _add_txn(db_session, late, 50000, "Other Income", tag="Kickstart", day=2)
        _add_txn(db_session, late, -20000, "Investments", tag="Pakam", day=5)

        goal = self._invest(service, early)

        assert goal["funded"] == 50000
        assert goal["to_invest"] == 30000

    def test_two_goals_on_one_investment_split_by_whose_income_paid(
        self, db_session, service
    ):
        """A funded goal takes what its income paid for; the plain goal takes the rest.

        Two goals counting every Investments transfer used to hand each one to
        the lower goal, so a gift invested after the second goal started never
        reached the goal it was given for.
        """
        before, start, after = _month_str(3), _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 100000)
        _add_txn(db_session, start, -6000, "Investments", tag="Pakam", day=5)
        _add_txn(db_session, start, 40000, "Investments", tag="Pakam", day=20)
        _add_txn(db_session, after, 200000, "Other Income", tag="Kickstart", day=2)
        _add_txn(db_session, after, -70000, "Investments", tag="Pakam", day=5)
        _add_txn(db_session, after, -135000, "Investments", tag="Pakam", day=25)

        self._invest(service, before)
        created = service.create(
            name="Yearly", target_amount=120000, kind="investment", start_month=start
        )

        goals = {g["name"]: g for g in created}
        assert [g["name"] for g in created] == ["Invest", "Yearly"]
        assert goals["Invest"]["funded"] == 200000
        assert goals["Invest"]["to_invest"] == 0
        # The plain goal takes the free cash in its waterfall turn, so it is
        # full; the deposit's uncovered 5000 is paid from what it holds.
        assert goals["Yearly"]["funded"] == 120000

    def test_it_takes_no_surplus_its_income_will_cover(self, db_session, service):
        """Income that meets the target keeps surplus away, even before it lands."""
        before, gifts = _month_str(2), _month_str(1)
        _seed_surplus(db_session, before, income=10000, expenses=6000)
        _add_txn(db_session, gifts, 200000, "Other Income", tag="Kickstart", day=2)

        goal = self._invest(service, before)

        assert goal["contributed"] == 200000
        assert goal["allocated"] == 0
        assert goal["is_achieved"] is True
        assert service.get_free_cash()["free_cash"] == 4000
        timeline = {row["month"]: row for row in service.get_timeline()["months"]}
        assert timeline[before]["goals"] == []

    def test_surplus_fills_only_what_its_income_leaves_short(self, db_session, service):
        """Free cash tops it up, in waterfall order, by exactly the gap."""
        before, gifts = _month_str(2), _month_str(1)
        _seed_surplus(db_session, before, income=10000, expenses=6000)
        _add_txn(db_session, gifts, 197000, "Other Income", tag="Kickstart", day=2)

        goal = self._invest(service, before)

        assert goal["contributed"] == 197000
        assert goal["allocated"] == 3000
        assert goal["funded"] == 200000
        assert service.get_free_cash()["free_cash"] == 1000

    def test_only_an_investment_goal_can_name_a_funding_income(self, service):
        """A cash goal is funded by surplus or its own saved-into rule, not this."""
        with pytest.raises(ValidationException):
            service.create(
                name="Trip",
                target_amount=1000,
                funding_category="Other Income",
            )

    def test_one_income_can_feed_only_one_goal(self, service):
        """The same income under two goals would be counted twice."""
        service.create(
            name="Kickstart",
            target_amount=1000,
            contribution_category="Other Income",
            contribution_tags="Kickstart",
        )
        with pytest.raises(ValidationException):
            self._invest(service, _month_str(1))

        # A different tag in the same category is a different income.
        goal = self._invest(service, _month_str(1), funding_tags="Bonus")
        assert goal["funding_tags"] == "Bonus"
        with pytest.raises(ValidationException):
            service.create(
                name="Bonus fund",
                target_amount=1000,
                contribution_category="Other Income",
            )


class TestChangingAGoalsKind:
    """A goal can switch between saving cash and investing."""

    def test_a_cash_goal_becomes_an_investment_goal(self, db_session, service):
        """Its cash settings are cleared and it counts investment transfers."""
        month = _month_str(1)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        transfer = _add_txn(db_session, month, -4000, "Investments", tag="Pakam", day=5)
        created = service.create(
            name="Goal",
            target_amount=20000,
            opening_balance=500,
            monthly_cap=1000,
            start_month=month,
            utilization_category="Leisure",
        )
        goal_id = created[0]["id"]
        service.link_transaction(
            goal_id=goal_id,
            source_type="transaction",
            source_id=transfer.unique_id,
            source_table="bank_transactions",
            link_type=LINK_CONTRIBUTION,
        )

        updated = service.update(goal_id, kind="investment")

        goal = next(g for g in updated if g["id"] == goal_id)
        assert goal["kind"] == "investment"
        assert goal["contribution_category"] == "Investments"
        assert goal["opening_balance"] == 0
        assert goal["monthly_cap"] is None
        assert goal["utilization_category"] is None
        assert service.get_links(goal_id) == []
        # Its history is restated: the month's 3000 surplus became cash it
        # invested, and the transfer's other 1000 came from free cash.
        assert goal["allocated"] == 3000
        assert goal["funded"] == 4000

    def test_an_investment_goal_becomes_a_cash_goal(self, db_session, service):
        """Its investment and funding rules are cleared and surplus fills it again."""
        month = _month_str(1)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        created = service.create(
            name="Goal",
            target_amount=20000,
            kind="investment",
            start_month=month,
            funding_category="Other Income",
        )
        goal_id = created[0]["id"]

        updated = service.update(goal_id, kind="cash")

        goal = next(g for g in updated if g["id"] == goal_id)
        assert goal["kind"] == "cash"
        assert goal["contribution_category"] is None
        assert goal["funding_category"] is None
        assert goal["funded"] == 3000

    def test_fields_sent_with_the_switch_apply(self, db_session, service):
        """A switch to cash can set the new kind's settings in the same save."""
        created = service.create(name="Goal", target_amount=1000, kind="investment")
        goal_id = created[0]["id"]

        updated = service.update(goal_id, kind="cash", monthly_cap=200)

        assert next(g for g in updated if g["id"] == goal_id)["monthly_cap"] == 200

    def test_a_closed_goal_must_be_reopened_first(self, db_session, service):
        """A closed goal's history is frozen, so its kind cannot change."""
        created = service.create(name="Goal", target_amount=1000)
        goal_id = created[0]["id"]
        service.close(goal_id)

        with pytest.raises(ValidationException):
            service.update(goal_id, kind="investment")


class TestEditingAGoalRestatesItsHistory:
    """An edit that decides what a goal got is applied to every month it covers."""

    def test_moving_the_start_later_clears_the_months_before_it(
        self, db_session, service
    ):
        """The months it no longer covers lose their rows; the pool reaches it later."""
        early, late = _month_str(2), _month_str(1)
        _seed_surplus(db_session, early, income=10000, expenses=6000)
        _seed_surplus(db_session, late, income=10000, expenses=7000)
        created = service.create(name="Trip", target_amount=50000, start_month=early)

        service.update(created[0]["id"], start_month=late)

        months = {m["month"]: m for m in service.get_timeline(months=0)["months"]}
        # The timeline now starts at the new start month.
        assert early not in months
        assert months[late]["goals"][0]["allocated"] == 7000

    def test_moving_the_start_earlier_fills_the_months_it_now_covers(
        self, db_session, service
    ):
        """Months before the old start join the goal's history."""
        early, late = _month_str(2), _month_str(1)
        _seed_surplus(db_session, early, income=10000, expenses=6000)
        _seed_surplus(db_session, late, income=10000, expenses=7000)
        created = service.create(name="Trip", target_amount=50000, start_month=late)

        service.update(created[0]["id"], start_month=early)

        months = {m["month"]: m for m in service.get_timeline(months=0)["months"]}
        assert months[early]["goals"][0]["allocated"] == 4000
        assert months[late]["goals"][0]["allocated"] == 3000

    def test_a_lower_target_hands_the_surplus_on_in_every_month(
        self, db_session, service
    ):
        """Shrinking the target restates the past, not just the months to come."""
        early, late = _month_str(2), _month_str(1)
        _seed_surplus(db_session, early, income=10000, expenses=6000)
        _seed_surplus(db_session, late, income=10000, expenses=7000)
        trip = service.create(name="Trip", target_amount=50000, start_month=early)[0]
        service.create(name="Car", target_amount=50000, start_month=early)

        updated = {g["name"]: g for g in service.update(trip["id"], target_amount=2000)}

        assert updated["Trip"]["funded"] == 2000
        assert updated["Car"]["funded"] == 5000

    def test_deleting_a_goal_hands_its_surplus_to_the_goals_below(
        self, db_session, service
    ):
        """What a deleted goal took goes to the next goal in line, month by month."""
        month = _month_str(1)
        _seed_surplus(db_session, month, income=10000, expenses=7000)
        trip = service.create(name="Trip", target_amount=50000, start_month=month)[0]
        service.create(name="Car", target_amount=50000, start_month=month)

        service.delete(trip["id"])

        assert service.get_all()[0]["funded"] == 3000


class TestNegativeFreeCash:
    """A pool below zero is shown, repaid first, and never claws back twice."""

    def test_a_new_overspend_after_the_hole_is_repaid_reaches_the_goals(
        self, db_session, service
    ):
        """Once a surplus repays the hole, this month's own overspend claws back."""
        bad, mixed = _month_str(2), _month_str(1)
        _seed_surplus(db_session, bad, income=0, expenses=3000)
        _seed_surplus(db_session, mixed, income=5000, expenses=0)
        _add_txn(db_session, mixed, -1500, "Wedding", day=20)

        service.create(
            name="Wedding",
            target_amount=10000,
            start_month=bad,
            utilization_category="Wedding",
        )

        goal = service.get_all()[0]
        # 5000 repays the 3000 hole; the goal takes the other 2000 and pays the
        # 1500 bill out of it.
        assert goal["funded"] == 2000
        assert goal["utilized"] == 1500
        assert service.get_free_cash()["free_cash"] == 0


class TestTargetDateEndsTheTurn:
    """A goal takes new money only up to its target month."""

    def test_surplus_after_the_target_month_goes_to_the_goals_below(
        self, db_session, service
    ):
        """A "last year" goal keeps what it got but stops starving the rest."""
        during, after = _month_str(2), _month_str(1)
        _seed_surplus(db_session, during, income=10000, expenses=6000)
        _seed_surplus(db_session, after, income=10000, expenses=7000)

        service.create(
            name="Last year",
            target_amount=50000,
            start_month=during,
            target_date=f"{during}-28",
        )
        service.create(name="Trip", target_amount=50000, start_month=during)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Last year"]["funded"] == 4000
        assert goals["Trip"]["funded"] == 3000

    def test_after_its_target_month_it_still_invests_what_it_holds(
        self, db_session, service
    ):
        """Its cash can still be invested; only new money passes it by."""
        during, after = _month_str(2), _month_str(1)
        _seed_surplus(db_session, during, income=10000, expenses=6000)
        _add_txn(db_session, after, -6000, "Investments", tag="Pakam", day=5)

        _create_investment_goal(
            service, start_month=during, target_date=f"{during}-28"
        )

        goal = service.get_all()[0]
        # It held 4000 and invested it; the other 2000 was new money it no
        # longer takes, so it left free cash.
        assert goal["funded"] == 4000
        assert goal["to_invest"] == 0
        assert service.get_free_cash()["free_cash"] == -2000


class TestClosedGoalReplay:
    """A goal that auto-closed replays its own history faithfully."""

    def test_a_closed_goal_keeps_the_bills_it_borrowed_for(self, db_session, service):
        """Once closed, later reads still see the bill it paid before its gifts.

        A closed goal used to be frozen from its first month, which skipped the
        borrowing that had paid its bill: the next read showed most of the bill
        as never paid out of it.
        """
        bill, gifts = _month_str(2), _month_str(1)
        _add_txn(db_session, bill, -12000, "Wedding", tag="Venue", day=9)
        _add_txn(db_session, gifts, 12000, "Other Income", tag="Wedding", day=6)
        created = service.create(
            name="Wedding",
            target_amount=12000,
            start_month=bill,
            contribution_category="Other Income",
            contribution_tags="Wedding",
            utilization_category="Wedding",
        )
        assert created[0]["is_closed"]

        for _ in range(2):
            goal = service.get_all()[0]
            assert goal["utilized"] == 12000
            assert goal["funded"] == 12000
            assert goal["owed"] == 0


class TestMoneyIsCountedOnce:
    """Regressions where money vanished from, or doubled in, the books."""

    def test_a_manual_deposit_is_paid_by_its_prior_wealth(self, db_session, service):
        """A manual deposit and its investment prior wealth cancel, as in net worth.

        A manual investment's deposits are tracked transactions, and its prior
        wealth (``-sum`` of them) is the money that paid for them outside any
        tracked account. Counting the deposits without the prior wealth took
        each one out of free cash with nothing to pay for it.
        """
        from backend.models.investment import Investment
        from backend.models.transaction import ManualInvestmentTransaction

        month = _month_str(1)
        _seed_free_cash(db_session, 10000)
        db_session.add(
            Investment(
                category="Investments",
                tag="Gemel",
                type="pension",
                name="Gemel",
                created_date=_day_in_month(month, 1),
                prior_wealth_amount=4000,
            )
        )
        db_session.add(
            ManualInvestmentTransaction(
                id="manual-1",
                date=_day_in_month(month, 3),
                provider="manual",
                account_name="Gemel",
                description="deposit",
                amount=-4000,
                category="Investments",
                tag="Gemel",
                source="manual_investment_transactions",
                type="normal",
            )
        )
        db_session.commit()

        service.create(name="Trip", target_amount=100000, start_month=month)
        assert service.get_free_cash()["liquid"] == 10000

        # And an investment goal counts the manual deposit as invested.
        created = service.create(
            name="Gemel goal", target_amount=50000, kind="investment", start_month=month
        )
        goal = next(g for g in created if g["name"] == "Gemel goal")
        assert goal["funded"] >= 4000

    def test_a_closed_goals_later_income_is_ordinary_money(self, db_session, service):
        """Gifts matching a closed goal's rule join the surplus, not the closed goal."""
        gifts, later = _month_str(2), _month_str(1)
        _add_txn(db_session, gifts, 3000, "Other Income", tag="Gift", day=3)
        _add_txn(db_session, gifts, -3000, "Wedding", day=9)
        _add_txn(db_session, later, 30000, "Other Income", tag="Gift", day=3)
        service.create(
            name="Small",
            target_amount=3000,
            start_month=gifts,
            contribution_category="Other Income",
            contribution_tags="Gift",
            utilization_category="Wedding",
        )

        # Filled and fully spent, it closes in the gifts month; the later gift
        # is ordinary income again.
        goal = service.get_all()[0]
        assert goal["is_closed"]
        assert goal["funded"] == 3000
        assert service.get_free_cash()["free_cash"] == 30000

    def test_income_before_a_goal_starts_stays_free_cash(self, db_session, service):
        """A saved-into rule claims no income from before its goal started."""
        before, start = _month_str(2), _month_str(1)
        _add_txn(db_session, before, 8000, "Other Income", tag="Gift", day=3)
        service.create(
            name="Wedding",
            target_amount=1000,
            start_month=start,
            contribution_category="Other Income",
            contribution_tags="Gift",
        )

        pool = service.get_free_cash()
        assert pool["liquid"] == 8000

    def test_a_link_before_the_goal_started_is_ordinary_spending(
        self, db_session, service
    ):
        """A bill linked from before the goal's start never left the books unpaid."""
        before, start = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 5000)
        bill = _add_txn(db_session, before, -2000, "Food", day=3)
        goal = service.create(name="Trip", target_amount=100000, start_month=start)[0]

        service.link_transaction(
            goal_id=goal["id"],
            source_type="transaction",
            source_id=bill.unique_id,
            source_table="bank_transactions",
            link_type=LINK_UTILIZATION,
        )

        assert service.get_all()[0]["utilized"] == 0
        assert service.get_free_cash()["liquid"] == 3000

    def test_a_reorder_rematches_shared_transfers(self, db_session, service):
        """After a reorder, a rebuild and a fresh read agree on shared transfers."""
        start, later = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 20000)
        _add_txn(db_session, start, 40000, "Other Income", tag="Kick", day=2)
        _add_txn(db_session, later, -30000, "Investments", tag="Pakam", day=5)
        plain = service.create(
            name="Plain", target_amount=50000, kind="investment", start_month=start
        )[0]
        funded = next(
            g
            for g in service.create(
                name="Funded",
                target_amount=50000,
                kind="investment",
                start_month=start,
                funding_category="Other Income",
                funding_tags="Kick",
            )
            if g["name"] == "Funded"
        )

        service.reorder([funded["id"], plain["id"]])
        service.rebuild()
        rebuilt = {g["name"]: g["to_invest"] for g in service.get_all()}
        fresh = {g["name"]: g["to_invest"] for g in SavingsGoalService(db_session).get_all()}

        assert rebuilt == fresh
