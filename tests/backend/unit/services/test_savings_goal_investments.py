"""Unit tests for investment-backed savings goals.

A goal can be backed by a holding the user intends to liquidate — bonds
earmarked for a car — instead of by cash. These cover what that backing does to
the goal's progress and to the surplus it still needs, and the two things it
must never do: enter the free-cash pool, or be clawed back by a deficit month.
"""

from datetime import date

import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.models.transaction import BankTransaction
from backend.services.savings_goal_service import SavingsGoalService


def _month_str(offset_back: int) -> str:
    """Return ``YYYY-MM`` for the month ``offset_back`` months before now."""
    today = date.today()
    month, year = today.month - offset_back, today.year
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def _add_txn(db, month: str, amount: float, category: str, day: int = 15):
    """Insert one bank transaction into a month."""
    db.add(
        BankTransaction(
            id=f"t-{month}-{amount}-{day}",
            date=f"{month}-{day:02d}",
            provider="TestBank",
            account_name="Main",
            description="test",
            amount=amount,
            category=category,
            source="bank_transactions",
            type="normal",
        )
    )
    db.commit()


def _seed_surplus(db, month: str, income: float, expenses: float) -> None:
    """Give a month a known realized surplus of ``income - expenses``."""
    _add_txn(db, month, income, "Salary", day=1)
    _add_txn(db, month, -expenses, "Food", day=2)


def _create_investment(db, value: float, name: str = "Bonds", tag: str = "Bonds") -> int:
    """Create an investment worth ``value``, priced by a balance snapshot."""
    inv = Investment(
        category="Investments",
        tag=tag,
        type="bonds",
        name=name,
        interest_rate_type="fixed",
        created_date="2024-01-01",
        is_closed=0,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    db.add(
        InvestmentBalanceSnapshot(
            investment_id=inv.id,
            date=date.today().strftime("%Y-%m-%d"),
            balance=value,
            source="manual",
        )
    )
    db.commit()
    return inv.id


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


class TestInvestmentBacking:
    """An earmarked holding funds a goal without being cash."""

    def test_backing_counts_toward_progress(self, db_session, service):
        """The holding's value shows as goal progress, valued live."""
        investment = _create_investment(db_session, 40000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment)

        goal = service.get_all()[0]
        assert goal["investment_backed"] == 40000
        assert goal["funded"] == 40000
        assert goal["remaining"] == 20000

    def test_backing_shrinks_what_the_surplus_must_cover(self, db_session, service):
        """A backed goal only draws the part the holding does not cover."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=5000)
        investment = _create_investment(db_session, 4000)

        goals = service.create(
            name="Car", target_amount=5000, priority=0, start_month=last
        )
        service.link_investment(goals[0]["id"], investment)
        service.rebuild()

        goal = service.get_all()[0]
        # 4000 is already backed, so only the last 1000 came out of the 5000
        # surplus — the rest spilled past the goal into the free-cash pool.
        assert goal["allocated"] == 1000
        assert goal["funded"] == 5000
        assert goal["is_achieved"] is True

    def test_backing_never_enters_the_free_cash_pool(self, db_session, service):
        """A bond is not spendable cash, so the pool must not count it."""
        last = _month_str(1)
        _seed_surplus(db_session, last, income=10000, expenses=7000)
        investment = _create_investment(db_session, 50000)

        goals = service.create(
            name="Car", target_amount=100000, priority=0, start_month=last
        )
        service.link_investment(goals[0]["id"], investment)

        pool = service.get_free_cash()
        # The goal took the whole 3000 surplus as cash; the 50000 bond is
        # reported apart from the liquid total, never inside it.
        assert pool["earmarked"] == 3000
        assert pool["liquid"] == 3000
        assert pool["free_cash"] == 0
        assert pool["investment_backed"] == 50000

    def test_deficit_never_claws_back_the_holding(self, db_session, service):
        """Overspending drains cash; it cannot reach into the bond."""
        good, bad = _month_str(2), _month_str(1)
        _seed_surplus(db_session, good, income=10000, expenses=9000)
        _seed_surplus(db_session, bad, income=5000, expenses=8000)
        investment = _create_investment(db_session, 25000)

        goals = service.create(
            name="Car", target_amount=100000, priority=0, start_month=good
        )
        service.link_investment(goals[0]["id"], investment)

        goal = service.get_all()[0]
        # The 1000 of cash the goal held was reclaimed; the 25000 backing was
        # untouched, so `funded` never drops below it.
        assert goal["clawed_back"] == 1000
        assert goal["investment_backed"] == 25000
        assert goal["funded"] == 25000

    def test_closing_the_investment_releases_the_backing(self, db_session, service):
        """Selling the holding drops its backing to zero on its own."""
        investment = _create_investment(db_session, 30000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment)
        assert service.get_all()[0]["investment_backed"] == 30000

        InvestmentsServiceClose(db_session, investment)

        fresh = SavingsGoalService(db_session)
        assert fresh.get_all()[0]["investment_backed"] == 0

    def test_partial_earmark_takes_only_what_it_asked_for(self, db_session, service):
        """An explicit amount earmarks part of a holding, not all of it."""
        investment = _create_investment(db_session, 80000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment, amount=25000)

        assert service.get_all()[0]["investment_backed"] == 25000


class TestBackingCapacity:
    """One holding can back several goals, but never more than it is worth."""

    def test_two_goals_share_one_holding(self, db_session, service):
        """Explicit amounts split a holding between goals."""
        investment = _create_investment(db_session, 50000)
        first = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        second = service.create(
            name="Trip", target_amount=60000, priority=1, start_month=_month_str(0)
        )
        service.link_investment(first[0]["id"], investment, amount=30000)
        service.link_investment(
            next(g["id"] for g in second if g["name"] == "Trip"), investment, amount=20000
        )

        goals = {g["name"]: g for g in service.get_all()}
        assert goals["Car"]["investment_backed"] == 30000
        assert goals["Trip"]["investment_backed"] == 20000

    def test_over_earmarking_a_holding_is_rejected(self, db_session, service):
        """Two goals cannot both count the same shekel of one holding."""
        investment = _create_investment(db_session, 50000)
        first = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        second = service.create(
            name="Trip", target_amount=60000, priority=1, start_month=_month_str(0)
        )
        service.link_investment(first[0]["id"], investment, amount=40000)

        trip_id = next(g["id"] for g in second if g["name"] == "Trip")
        with pytest.raises(ValidationException, match="still unearmarked"):
            service.link_investment(trip_id, investment, amount=20000)

    def test_second_whole_holding_earmark_is_rejected(self, db_session, service):
        """Only one goal may claim "whatever is left" of a holding."""
        investment = _create_investment(db_session, 50000)
        first = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        second = service.create(
            name="Trip", target_amount=60000, priority=1, start_month=_month_str(0)
        )
        service.link_investment(first[0]["id"], investment)

        trip_id = next(g["id"] for g in second if g["name"] == "Trip")
        with pytest.raises(ValidationException, match="remainder"):
            service.link_investment(trip_id, investment)

    def test_a_shrunken_holding_shortchanges_the_newer_claim(self, db_session, service):
        """When value falls, the earlier earmark keeps its share."""
        investment = _create_investment(db_session, 50000)
        first = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        second = service.create(
            name="Trip", target_amount=60000, priority=1, start_month=_month_str(0)
        )
        service.link_investment(first[0]["id"], investment, amount=30000)
        trip_id = next(g["id"] for g in second if g["name"] == "Trip")
        service.link_investment(trip_id, investment, amount=20000)

        # The market halves the holding. One snapshot per investment per
        # date, so today's is repriced rather than duplicated.
        snapshot = (
            db_session.query(InvestmentBalanceSnapshot)
            .filter(InvestmentBalanceSnapshot.investment_id == investment)
            .one()
        )
        snapshot.balance = 25000
        db_session.commit()

        goals = {g["name"]: g for g in SavingsGoalService(db_session).get_all()}
        assert goals["Car"]["investment_backed"] == 25000
        assert goals["Trip"]["investment_backed"] == 0

    def test_closed_investment_cannot_back_a_goal(self, db_session, service):
        """A sold holding is not collateral for anything."""
        investment = _create_investment(db_session, 10000)
        InvestmentsServiceClose(db_session, investment)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )

        with pytest.raises(ValidationException, match="closed"):
            service.link_investment(goals[0]["id"], investment)

    def test_unknown_investment_is_rejected(self, db_session, service):
        """Earmarking something that does not exist is a 404, not a crash."""
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        with pytest.raises(EntityNotFoundException):
            service.link_investment(goals[0]["id"], 9999)


class TestBackingListings:
    """What the pickers and the goal detail read back."""

    def test_available_investments_report_their_headroom(self, db_session, service):
        """A partly earmarked holding offers only what is left of it."""
        investment = _create_investment(db_session, 50000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment, amount=30000)

        row = next(
            r for r in service.get_available_investments() if r["id"] == investment
        )
        assert row["value"] == 50000
        assert row["earmarked"] == 30000
        assert row["available"] == 20000
        assert row["fully_claimed"] is False

    def test_whole_holding_earmark_leaves_no_headroom(self, db_session, service):
        """A holding claimed in full offers nothing to the next goal."""
        investment = _create_investment(db_session, 50000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment)

        row = next(
            r for r in service.get_available_investments() if r["id"] == investment
        )
        assert row["fully_claimed"] is True
        assert row["available"] == 0

    def test_unlinking_releases_the_holding(self, db_session, service):
        """Releasing an earmark returns the goal's progress and the headroom."""
        investment = _create_investment(db_session, 50000)
        goals = service.create(
            name="Car", target_amount=60000, priority=0, start_month=_month_str(0)
        )
        service.link_investment(goals[0]["id"], investment)

        backings = service.get_investment_backings()
        assert len(backings) == 1
        assert backings[0]["investment_name"] == "Bonds"
        assert backings[0]["amount"] is None

        service.unlink_investment(backings[0]["id"])
        assert service.get_all()[0]["investment_backed"] == 0
        assert service.get_investment_backings() == []


def InvestmentsServiceClose(db_session, investment_id: int) -> None:
    """Close an investment the way the investments service does."""
    from backend.services.investments import InvestmentsService

    InvestmentsService(db_session).close_investment(
        investment_id, date.today().strftime("%Y-%m-%d")
    )
