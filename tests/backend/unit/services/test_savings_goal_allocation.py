"""Unit tests for the savings-goal allocation engine.

Covers the waterfall itself — priority order, per-goal monthly caps, spillover
— plus the rules that surround it: contributions consuming the month's surplus
before the waterfall runs, utilizations drawing a goal down without touching
its target, negative-surplus months draining the free-cash pool before they
reach any goal, auto-closure, and the immutability of a closed goal's history
across a rebuild.
"""

from datetime import date

import pytest

from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
)
from backend.models.bank_balance import BankBalance
from backend.models.transaction import BankTransaction
from backend.services.savings_goal_service import SavingsGoalService


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

    def test_higher_priority_goal_fills_first(self, db_session, service):
        """The top-priority goal absorbs the surplus before the next one sees any."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)

        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["First"]["funded"] == 1000
        assert goals["Second"]["funded"] == 1000

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
        assert goal["funded"] == 1200


class TestSurplusDefinition:
    """What counts as the month's spare money."""

    def test_negative_surplus_month_allocates_nothing(self, db_session, service):
        """Overspending a month funds no goals — the deficit hits the pool."""
        good, bad = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 50000)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        goal = service.get_all()[0]
        assert goal["funded"] == 1000
        assert goal["clawed_back"] == 0

    def test_investment_transfers_reduce_the_surplus(self, db_session, service):
        """Money moved into investments has left the spendable pool."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        _add_txn(db_session, last, -2000, "Investments", day=3)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=last)

        assert service.get_all()[0]["funded"] == 1000

    def test_goal_starts_after_start_month_ignores_earlier_surplus(
        self, db_session, service
    ):
        """A goal never claims surpluses from months that predate it."""
        _seed_surplus(db_session, _month_str(3), income=10000, expenses=5000)
        _seed_surplus(db_session, _month_str(1), income=10000, expenses=9800)

        service.create(
            name="Late", target_amount=5000, priority=0, start_month=_month_str(1)
        )

        assert service.get_all()[0]["funded"] == 200


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
        # 600 of contribution plus the remaining 2400 of a 3000 pool.
        assert goal["funded"] == 3000


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


class TestRebuild:
    """Restating history is explicit, previewable, and respects closed goals."""

    def test_priority_change_alone_does_not_restate_history(self, db_session, service):
        """Reordering applies forward; already-written months keep their amounts."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        first = service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)

        before = {g["name"]: g["funded"] for g in service.get_all()}
        assert before == {"First": 500, "Second": 0}

        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.reorder([ids["Second"], ids["First"]])

        after = {g["name"]: g["funded"] for g in service.get_all()}
        assert after == before

    def test_rebuild_dry_run_previews_without_writing(self, db_session, service):
        """A dry run reports the diff and leaves the ledger untouched."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=9500)
        service.create(name="First", target_amount=1000, priority=0, start_month=last)
        service.create(name="Second", target_amount=1000, priority=1, start_month=last)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.reorder([ids["Second"], ids["First"]])

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
        service.reorder([ids["Second"], ids["First"]])

        service.rebuild(dry_run=False)

        after = {g["name"]: g["funded"] for g in service.get_all()}
        assert after == {"First": 0, "Second": 500}

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
        service.rebuild(dry_run=False)
        assert {g["name"]: g["funded"] for g in service.get_all()}["Done"] == 500

        service.close(done_id)
        ids = {g["name"]: g["id"] for g in service.get_all()}
        service.reorder([ids["Other"], ids["Done"]])
        service.rebuild(dry_run=False)

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
        assert goal["funded"] == 1000
        assert goal["clawed_back"] == 0
        # 20000 opening + 1000 - 3000, less the 1000 the goal earmarked.
        assert service.get_free_cash()["free_cash"] == 17000

    def test_goals_absorb_only_what_the_pool_could_not(self, db_session, service):
        """Once the pool is dry the remainder comes out of the goals."""
        good, bad = _month_str(2), _month_str(1)
        _seed_free_cash(db_session, 500)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)

        service.create(name="Goal", target_amount=5000, priority=0, start_month=good)

        goal = service.get_all()[0]
        # Pool holds 500 opening + 0 unallocated; the 3000 deficit empties it
        # and takes the remaining 2500 from the goal, which only had 1000.
        assert goal["clawed_back"] == 1000
        assert goal["funded"] == 0
        assert service.get_free_cash()["free_cash"] == 0

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
            "investment_backed": 0.0,
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
        assert view["free_cash"] == 0
        assert view["goals"][0]["allocated"] == -1000
