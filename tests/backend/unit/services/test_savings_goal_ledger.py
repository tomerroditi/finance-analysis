"""Unit tests for what each savings goal holds, and the free cash beside them.

A goal holds what the user put in, plus its own income, less what it paid;
free cash is the bank and cash money no goal holds. Nothing moves unless the
user asks: these tests pin each rule, the cover plan and month-by-month reads.
"""

from datetime import date

import pytest

from backend.errors import ValidationException
from backend.models.bank_balance import BankBalance
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.savings_goals import SavingsGoalService


def _month(offset_back: int) -> str:
    """``YYYY-MM`` for the month ``offset_back`` months before this one."""
    today = date.today()
    month, year = today.month - offset_back, today.year
    while month <= 0:
        month, year = month + 12, year - 1
    return f"{year:04d}-{month:02d}"


def _bank(db, month: str, amount: float, category: str, tag=None, day: int = 15):
    """Insert one bank transaction and return it."""
    txn = BankTransaction(
        id=f"t-{month}-{amount}-{day}-{category}",
        date=f"{month}-{day:02d}",
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


def _card(db, month: str, amount: float, category: str, day: int = 15):
    """Insert one itemized credit-card purchase and return it."""
    txn = CreditCardTransaction(
        id=f"cc-{month}-{amount}-{day}",
        date=f"{month}-{day:02d}",
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
    return txn


def _liquid(db, amount: float) -> None:
    """Put ``amount`` in the bank from before tracking began."""
    db.add(
        BankBalance(
            provider="TestBank",
            account_name="Main",
            balance=amount,
            prior_wealth_amount=amount,
        )
    )
    db.commit()


def _goal(goals: list[dict], name: str) -> dict:
    """The goal called ``name`` in a service response."""
    return next(g for g in goals if g["name"] == name)


@pytest.fixture
def service(db_session):
    """A service bound to the in-memory test database."""
    return SavingsGoalService(db_session)


class TestMoneyInAndOut:
    """A goal holds exactly what the user put in and took out."""

    def test_adding_money_fills_the_goal_and_leaves_free_cash(self, db_session, service):
        """Money put into a goal moves out of free cash, nowhere else."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000)[0]

        goal = service.add_entry(goal["id"], 3000)[0]

        assert goal["available"] == 3000
        assert goal["saved"] == 3000
        assert goal["remaining"] == 2000
        assert service.get_free_cash()["free_cash"] == 7000

    def test_taking_money_out_returns_it_to_free_cash(self, db_session, service):
        """A negative entry hands money back."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000, initial_amount=3000)[0]

        goal = service.add_entry(goal["id"], -1000)[0]

        assert goal["available"] == 2000
        assert service.get_free_cash()["free_cash"] == 8000

    def test_cannot_take_out_more_than_the_goal_holds(self, db_session, service):
        """Taking out more than is there is refused."""
        goal = service.create(name="Trip", target_amount=5000, initial_amount=1000)[0]

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], -1500)

    def test_zero_is_not_an_entry(self, service):
        """An empty move is refused."""
        goal = service.create(name="Trip", target_amount=5000)[0]

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], 0)

    def test_deleting_an_entry_undoes_it(self, db_session, service):
        """Undo removes the entry and its money."""
        goal = service.create(name="Trip", target_amount=5000)[0]
        goal = service.add_entry(goal["id"], 700)[0]

        goal = service.delete_entry(goal["entries"][0]["id"])[0]

        assert goal["available"] == 0
        assert goal["entries"] == []

    def test_entries_come_back_newest_first(self, service):
        """The goal lists its entries with the latest on top."""
        goal = service.create(name="Trip", target_amount=5000)[0]
        service.add_entry(goal["id"], 100, entry_date="2025-01-10")
        goal = service.add_entry(goal["id"], 200, entry_date="2025-03-10")[0]

        assert [e["amount"] for e in goal["entries"]] == [200, 100]

    def test_free_cash_can_go_negative(self, db_session, service):
        """Setting aside more than there is shows as a shortfall, never hidden."""
        _liquid(db_session, 1000)
        service.create(name="Trip", target_amount=5000, initial_amount=3000)

        free = service.get_free_cash()

        assert free["free_cash"] == -2000
        assert free["shortfall"] == 2000


class TestSpendingOutOfAGoal:
    """Linked spending draws a goal down; what it cannot pay is free cash's."""

    def test_linked_spending_draws_the_goal_down(self, db_session, service):
        """A purchase the goal pays for leaves the goal, not free cash."""
        _liquid(db_session, 20000)
        month = _month(0)
        goal = service.create(
            name="Trip", target_amount=5000, initial_amount=4000, start_month=month
        )[0]
        service.set_spending_link(goal["id"], "Travel")
        _bank(db_session, month, -1500, "Travel", day=20)

        service._invalidate()
        goal = _goal(service.get_all(), "Trip")

        assert goal["spent"] == 1500
        assert goal["available"] == 2500
        assert goal["saved"] == 4000
        assert service.get_free_cash()["free_cash"] == 20000 - 1500 - 2500

    def test_a_goal_without_income_never_goes_below_zero(self, db_session, service):
        """A bill beyond what the goal holds is paid by free cash for good."""
        _liquid(db_session, 20000)
        month = _month(1)
        goal = service.create(name="Trip", target_amount=5000, start_month=month)[0]
        service.add_entry(goal["id"], 1000, entry_date=f"{month}-05")
        service.set_spending_link(goal["id"], "Travel")
        _bank(db_session, month, -3000, "Travel", day=20)

        service._invalidate()
        goal = _goal(service.get_all(), "Trip")
        assert goal["available"] == 0
        assert goal["owed"] == 0
        assert goal["spent"] == 1000

        # A later deposit is new money, not a repayment of that bill.
        goal = service.add_entry(goal["id"], 500)[0]
        assert goal["available"] == 500

    def test_a_refund_comes_back_to_the_goal(self, db_session, service):
        """Refunds net against the purchase they repay."""
        month = _month(0)
        goal = service.create(
            name="Trip", target_amount=5000, initial_amount=2000, start_month=month
        )[0]
        service.set_spending_link(goal["id"], "Travel")
        _bank(db_session, month, -1500, "Travel", day=10)
        _bank(db_session, month, 500, "Travel", day=12)

        service._invalidate()
        goal = _goal(service.get_all(), "Trip")

        assert goal["spent"] == 1000
        assert goal["available"] == 1000

    def test_a_card_purchase_is_paid_by_its_goal(self, db_session, service):
        """Itemized card purchases can be paid out of a goal too."""
        month = _month(0)
        goal = service.create(
            name="Trip", target_amount=5000, initial_amount=2000, start_month=month
        )[0]
        service.set_spending_link(goal["id"], "Travel")
        _card(db_session, month, -800, "Travel")

        service._invalidate()
        goal = _goal(service.get_all(), "Trip")

        assert goal["spent"] == 800

    def test_spending_before_the_goal_started_is_not_its(self, db_session, service):
        """The rule claims from the start month on."""
        goal = service.create(
            name="Trip", target_amount=5000, initial_amount=2000, start_month=_month(0)
        )[0]
        service.set_spending_link(goal["id"], "Travel")
        _bank(db_session, _month(2), -800, "Travel")

        service._invalidate()
        assert _goal(service.get_all(), "Trip")["spent"] == 0


class TestGoalsWithIncomeOfTheirOwn:
    """A saved-into goal is filled by its income, and may spend ahead of it."""

    def test_income_fills_the_goal_without_touching_free_cash(self, db_session, service):
        """Gifts land in the bank and in the goal at once."""
        _liquid(db_session, 10000)
        month = _month(0)
        service.create(
            name="Wedding",
            target_amount=50000,
            start_month=month,
            contribution_category="Other Income",
            contribution_tags="Wedding",
        )
        _bank(db_session, month, 20000, "Other Income", tag="Wedding")

        service._invalidate()
        goal = _goal(service.get_all(), "Wedding")

        assert goal["income"] == 20000
        assert goal["available"] == 20000
        assert service.get_free_cash()["free_cash"] == 10000

    def test_bills_before_the_income_are_owed_then_repaid(self, db_session, service):
        """Spending ahead of the gifts is a loan the gifts repay."""
        _liquid(db_session, 50000)
        earlier, later = _month(2), _month(1)
        goal = service.create(
            name="Wedding",
            target_amount=50000,
            start_month=earlier,
            contribution_category="Other Income",
            contribution_tags="Wedding",
        )[0]
        service.set_spending_link(goal["id"], "Wedding")
        _bank(db_session, earlier, -30000, "Wedding")

        service._invalidate()
        goal = _goal(service.get_all(), "Wedding")
        assert goal["owed"] == 30000
        assert goal["available"] == 0
        assert service.get_free_cash()["free_cash"] == 20000

        _bank(db_session, later, 40000, "Other Income", tag="Wedding")
        service._invalidate()
        goal = _goal(service.get_all(), "Wedding")
        assert goal["owed"] == 0
        assert goal["available"] == 10000
        assert service.get_free_cash()["free_cash"] == 50000


class TestCover:
    """A shortfall is covered only when the user asks, lowest goal first."""

    def test_the_plan_takes_from_the_lowest_goal_first(self, db_session, service):
        """The bottom of the list gives back before anything above it."""
        _liquid(db_session, 5000)
        service.create(name="Top", target_amount=10000, initial_amount=4000)
        service.create(name="Bottom", target_amount=10000, initial_amount=2000)

        plan = service.get_free_cash()["cover_plan"]

        assert [(p["name"], p["amount"]) for p in plan] == [("Bottom", 1000)]

    def test_the_plan_moves_up_the_list_when_a_goal_runs_dry(self, db_session, service):
        """No goal gives more than it holds."""
        _liquid(db_session, 1000)
        service.create(name="Top", target_amount=10000, initial_amount=4000)
        service.create(name="Bottom", target_amount=10000, initial_amount=2000)

        plan = service.get_free_cash()["cover_plan"]

        assert [(p["name"], p["amount"]) for p in plan] == [
            ("Bottom", 2000),
            ("Top", 3000),
        ]

    def test_covering_applies_the_plan(self, db_session, service):
        """After covering, free cash is back at zero and the entries say why."""
        _liquid(db_session, 5000)
        service.create(name="Top", target_amount=10000, initial_amount=4000)
        service.create(name="Bottom", target_amount=10000, initial_amount=2000)

        goals = service.cover()

        bottom = _goal(goals, "Bottom")
        assert bottom["available"] == 1000
        assert bottom["entries"][0]["source"] == "cover"
        assert service.get_free_cash()["free_cash"] == 0
        assert service.get_free_cash()["cover_plan"] == []

    def test_nothing_to_cover_when_free_cash_is_positive(self, db_session, service):
        """No shortfall, no plan."""
        _liquid(db_session, 10000)
        service.create(name="Top", target_amount=10000, initial_amount=4000)

        assert service.get_free_cash()["cover_plan"] == []


class TestFund:
    """Funding puts the month's suggestion in, as far as free cash goes."""

    def test_funds_the_monthly_amount(self, db_session, service):
        """A goal with a monthly amount is offered and given it."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000, monthly_amount=800)[0]
        assert goal["suggested_this_month"] == 800

        goal = service.fund([goal["id"]])[0]

        assert goal["available"] == 800
        assert goal["suggested_this_month"] == 0

    def test_a_partial_deposit_leaves_the_rest_suggested(self, db_session, service):
        """Putting in part of the month's amount leaves the rest on offer."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000, monthly_amount=800)[0]

        goal = service.add_entry(goal["id"], 300)[0]

        assert goal["suggested_this_month"] == 500

    def test_never_suggests_past_the_target(self, db_session, service):
        """The last month only asks for what is left."""
        goal = service.create(name="Trip", target_amount=5000, monthly_amount=800)[0]

        goal = service.add_entry(goal["id"], 4800, entry_date="2020-01-01")[0]

        assert goal["suggested_this_month"] == 200

    def test_fund_all_stops_when_free_cash_runs_out(self, db_session, service):
        """The top of the list is funded first; nothing drives free cash negative."""
        _liquid(db_session, 1000)
        service.create(name="Top", target_amount=5000, monthly_amount=800)
        service.create(name="Bottom", target_amount=5000, monthly_amount=800)

        goals = service.fund(None)

        assert _goal(goals, "Top")["available"] == 800
        assert _goal(goals, "Bottom")["available"] == 200
        assert service.get_free_cash()["free_cash"] == 0

    def test_a_target_date_suggests_what_it_needs(self, db_session, service):
        """Without a monthly amount, the target date sizes the suggestion."""
        today = date.today()
        target = date(today.year + 1, today.month, 1).isoformat()
        goal = service.create(name="Trip", target_amount=12000, target_date=target)[0]

        assert goal["suggested_this_month"] > 0
        assert goal["suggested_this_month"] == pytest.approx(goal["monthly_needed"], abs=1)

    def test_a_closed_or_achieved_goal_suggests_nothing(self, db_session, service):
        """Nothing is offered to a goal that is done."""
        goal = service.create(
            name="Trip", target_amount=500, monthly_amount=800, initial_amount=500
        )[0]

        assert goal["is_achieved"]
        assert goal["suggested_this_month"] == 0


class TestCloseAndReopen:
    """Closing hands the money back; reopening restores it."""

    def test_close_returns_the_money_to_free_cash(self, db_session, service):
        """A closed goal holds nothing."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000, initial_amount=3000)[0]

        goal = service.close(goal["id"])[0]

        assert goal["is_closed"]
        assert goal["available"] == 0
        assert service.get_free_cash()["free_cash"] == 10000

    def test_reopen_restores_what_closing_handed_back(self, db_session, service):
        """Reopening undoes the hand-back."""
        _liquid(db_session, 10000)
        goal = service.create(name="Trip", target_amount=5000, initial_amount=3000)[0]
        service.close(goal["id"])

        goal = service.reopen(goal["id"])[0]

        assert goal["available"] == 3000
        assert service.get_free_cash()["free_cash"] == 7000

    def test_a_closed_goal_takes_no_money(self, db_session, service):
        """Money cannot move into a closed goal."""
        goal = service.create(name="Trip", target_amount=5000)[0]
        service.close(goal["id"])

        with pytest.raises(ValidationException):
            service.add_entry(goal["id"], 100)


class TestMonthByMonth:
    """The timeline and the month view read the same ledger."""

    def test_timeline_reports_balances_changes_and_free_cash(self, db_session, service):
        """Each month carries what every goal held at its end, and free cash."""
        _liquid(db_session, 10000)
        two_ago, last = _month(2), _month(1)
        goal = service.create(name="Trip", target_amount=5000, start_month=two_ago)[0]
        service.add_entry(goal["id"], 1000, entry_date=f"{two_ago}-05")
        service.add_entry(goal["id"], 500, entry_date=f"{last}-05")

        timeline = service.get_timeline(0)
        by_month = {row["month"]: row for row in timeline["months"]}

        assert by_month[two_ago]["goals"][0] == {
            "goal_id": goal["id"],
            "balance": 1000,
            "change": 1000,
        }
        assert by_month[last]["goals"][0]["balance"] == 1500
        assert by_month[last]["goals"][0]["change"] == 500
        assert by_month[last]["free_cash"] == 8500
        assert timeline["total_months"] == 3

    def test_free_cash_follows_the_bank_month_by_month(self, db_session, service):
        """A month's free cash is what the accounts held then, less the goals."""
        _liquid(db_session, 10000)
        last = _month(1)
        service.create(name="Trip", target_amount=5000, start_month=last)
        _bank(db_session, last, 3000, "Salary", day=1)
        _bank(db_session, _month(0), -2000, "Food", day=1)

        service._invalidate()
        rows = {r["month"]: r for r in service.get_timeline(0)["months"]}

        assert rows[last]["free_cash"] == 13000
        assert rows[_month(0)]["free_cash"] == 11000

    def test_month_view_splits_added_income_and_spent(self, db_session, service):
        """The budget page sees what moved into and out of each goal."""
        month = _month(0)
        goal = service.create(
            name="Trip", target_amount=5000, initial_amount=2000, start_month=month
        )[0]
        service.set_spending_link(goal["id"], "Travel")
        _bank(db_session, month, -500, "Travel")

        service._invalidate()
        view = service.get_month(int(month[:4]), int(month[5:]))

        assert view["goals"] == [
            {
                "goal_id": goal["id"],
                "name": "Trip",
                "priority": 0,
                "status": "active",
                "added": 2000,
                "income": 0,
                "spent": 500,
                "change": 1500,
            }
        ]
        assert view["total_added"] == 2000

    def test_a_quiet_month_lists_no_goals(self, service):
        """Goals with no movement stay off the month view."""
        service.create(name="Trip", target_amount=5000)

        assert service.get_month(2001, 1)["goals"] == []


class TestLinks:
    """Only income can be saved into a goal by a link."""

    def test_an_outgoing_transaction_cannot_be_a_contribution(self, db_session, service):
        """Setting money aside is an entry, not a link."""
        goal = service.create(name="Trip", target_amount=5000)[0]
        txn = _bank(db_session, _month(0), -1000, "Transfers")

        with pytest.raises(ValidationException):
            service.link_transaction(
                goal["id"], "transaction", txn.unique_id, "bank_transactions", "contribution"
            )

    def test_an_incoming_transaction_can_be(self, db_session, service):
        """A gift linked to a goal is its income."""
        goal = service.create(name="Trip", target_amount=5000, start_month=_month(0))[0]
        txn = _bank(db_session, _month(0), 1000, "Other Income")

        goal = service.link_transaction(
            goal["id"], "transaction", txn.unique_id, "bank_transactions", "contribution"
        )[0]

        assert goal["income"] == 1000
        assert goal["available"] == 1000
