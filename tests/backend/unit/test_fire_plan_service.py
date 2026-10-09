"""The early-retirement plan: filled from tracked data, saved, and kept in step.

`FirePlanService` turns what the app tracks into the calculator's flat form.
These seed one of each kind of tracked account and check the form it builds,
that a saved plan follows its linked fields and sourced rows but nothing else,
and that the old retirement goal seeds a first plan.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance
from backend.models.cash_balance import CashBalance
from backend.models.insurance_account import InsuranceAccount
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.models.liability import Liability
from backend.models.retirement_goal import RetirementGoal
from backend.services.fire_plan_service import FirePlanService


@pytest.fixture
def tracked(db_session: Session) -> dict:
    """One of each account the plan follows: cash, a portfolio, a keren, a pension, a loan."""
    db_session.add_all(
        [
            BankBalance(provider="hapoalim", account_name="Checking", balance=50_000.0),
            CashBalance(account_name="Wallet", balance=1_000.0),
            InsuranceAccount(
                provider="mislaka",
                policy_id="P-1",
                policy_type="pension",
                account_name="Pension",
                balance=400_000.0,
                commission_savings_pct=0.2,
                commission_deposits_pct=1.5,
            ),
        ]
    )
    stocks = Investment(
        category="Investments",
        tag="Stocks",
        type="stocks",
        name="Index fund",
        created_date="2024-01-01",
        commission_management=0.07,
    )
    keren = Investment(
        category="Investments",
        tag="KH",
        type="hishtalmut",
        name="Keren",
        created_date="2024-01-01",
    )
    loan = Liability(
        name="Mortgage",
        category="Liabilities",
        tag="Mortgage",
        principal_amount=600_000.0,
        interest_rate=4.0,
        term_months=240,
        start_date="2022-05-01",
        created_date="2022-05-01",
    )
    db_session.add_all([stocks, keren, loan])
    db_session.flush()
    db_session.add_all(
        [
            InvestmentBalanceSnapshot(
                investment_id=stocks.id, date="2024-06-01", balance=200_000.0
            ),
            InvestmentBalanceSnapshot(
                investment_id=keren.id, date="2024-06-01", balance=80_000.0
            ),
        ]
    )
    db_session.commit()
    return {"stocks": stocks, "keren": keren, "loan": loan}


def _service(db_session: Session) -> FirePlanService:
    return FirePlanService(db_session)


class TestTrackedData:
    """What tracked data becomes, in the calculator's field names."""

    def test_cash_is_bank_plus_cash(self, db_session: Session, tracked: dict) -> None:
        """The cash balance sums every bank and cash account."""
        assert _service(db_session).tracked().scalars["balance"] == "51000"

    def test_pension_balance_and_fees(self, db_session: Session, tracked: dict) -> None:
        """The pension fund carries its balance and both fees."""
        scalars = _service(db_session).tracked().scalars
        assert scalars["pensionBalance"] == "400000"
        assert (scalars["pensionFee1"], scalars["pensionFee2"]) == ("0.2", "1.5")

    def test_investment_is_a_portfolio_row(self, db_session: Session, tracked: dict) -> None:
        """An open investment is a sourced portfolio row seeded with its own fee."""
        (row,) = _service(db_session).tracked().rows["portfolio"]
        assert row.source == f"investment:{tracked['stocks'].id}"
        assert row.fields["portfolioBalance"] == "200000"
        assert row.seed["portfolioFee"] == "0.07"

    def test_keren_is_its_own_section(self, db_session: Session, tracked: dict) -> None:
        """A keren hishtalmut is a keren row, never a portfolio."""
        rows = _service(db_session).tracked().rows
        assert [r.label for r in rows["keren"]] == ["Keren"]
        assert all(r.label != "Keren" for r in rows["portfolio"])

    def test_liability_is_a_loan_row(self, db_session: Session, tracked: dict) -> None:
        """An active liability is a Spitzer loan with its own term and rate."""
        (row,) = _service(db_session).tracked().rows["loan"]
        assert row.fields["debtInitialSum"] == "600000"
        assert row.fields["debtTotalPeriod"] == "20"
        assert row.fields["debtType"] == "spitzer"

    def test_empty_database(self, db_session: Session) -> None:
        """A fresh install derives a plan without error, with nothing to follow."""
        plan = _service(db_session).get_plan()
        assert plan["saved"] is False
        assert plan["fields"]["balance"] == "0"
        assert all(rows == [] for rows in plan["tracked"]["rows"].values())


class TestDerivedPlan:
    """The plan offered before anything is saved."""

    def test_every_tracked_account_is_a_sourced_row(
        self, db_session: Session, tracked: dict
    ) -> None:
        """Each tracked row lands in the form with its seed and its source."""
        fields = _service(db_session).get_plan()["fields"]
        assert fields["num_portfolio_fields"] == "1"
        assert fields["portfolioSource1"] == f"investment:{tracked['stocks'].id}"
        assert fields["portfolioDescription1"] == "Index fund"
        assert fields["num_keren_fields"] == "1"
        assert fields["num_loan_fields"] == "1"

    def test_scalars_start_linked(self, db_session: Session, tracked: dict) -> None:
        """Every tracked single-value field starts out following tracked data."""
        plan = _service(db_session).get_plan()
        assert {"balance", "pensionBalance"} <= set(plan["linked"])

    def test_no_date_of_birth_is_not_runnable(
        self, db_session: Session, tracked: dict
    ) -> None:
        """Tracked data carries no date of birth, so the plan cannot run yet."""
        assert _service(db_session).runnable_fields() is None

    def test_old_goal_seeds_age_target_and_spending(self, db_session: Session) -> None:
        """The old retirement goal's age, target and both spending figures carry over."""
        db_session.add(
            RetirementGoal(
                current_age=40,
                gender="female",
                target_retirement_age=55,
                monthly_expenses_in_retirement=14_000.0,
                monthly_expenses_override=20_000.0,
            )
        )
        db_session.commit()
        fields = _service(db_session).get_plan()["fields"]
        today = date.today()
        assert fields["dateOfBirth"] == date(today.year - 40, today.month, 1).isoformat()
        assert (fields["gender"], fields["base_problem_max_age"]) == ("female", "55")
        assert fields["num_expense_fields"] == "2"
        assert (fields["expenseSum1"], fields["expenseEndType1"]) == ("20000", "fire")
        assert (fields["expenseSum2"], fields["expenseStartType2"]) == ("14000", "fire")


class TestSavedPlan:
    """A saved plan follows what is linked and sourced, and nothing else."""

    def test_linked_scalar_follows_tracked_data(
        self, db_session: Session, tracked: dict
    ) -> None:
        """A linked cash balance is refreshed when the bank balance moves."""
        service = _service(db_session)
        plan = service.get_plan()
        service.save_plan(plan["fields"], plan["linked"])
        db_session.query(BankBalance).update({"balance": 70_000.0})
        db_session.commit()
        assert service.get_plan()["fields"]["balance"] == "71000"

    def test_unlinked_scalar_keeps_the_users_value(
        self, db_session: Session, tracked: dict
    ) -> None:
        """A field the user took off the list keeps what they typed."""
        service = _service(db_session)
        plan = service.get_plan()
        fields = {**plan["fields"], "balance": "5000"}
        service.save_plan(fields, [n for n in plan["linked"] if n != "balance"])
        assert service.get_plan()["fields"]["balance"] == "5000"

    def test_sourced_row_refreshes_only_its_tracked_fields(
        self, db_session: Session, tracked: dict
    ) -> None:
        """A sourced row's balance follows the account; the return the user typed stays."""
        service = _service(db_session)
        fields = {**service.get_plan()["fields"], "portfolioInterest1": "7.5",
                  "portfolioBalance1": "1"}
        service.save_plan(fields, [])
        refreshed = service.get_plan()["fields"]
        assert refreshed["portfolioBalance1"] == "200000"
        assert refreshed["portfolioInterest1"] == "7.5"

    def test_row_of_a_vanished_account_is_dropped(
        self, db_session: Session, tracked: dict
    ) -> None:
        """A paid-off loan leaves the plan; the rows after it close up."""
        service = _service(db_session)
        fields = {
            **service.get_plan()["fields"],
            "num_loan_fields": "2",
            "debtStartDate2": "2025-01-01",
            "debtInitialSum2": "10000",
            "debtTotalPeriod2": "2",
        }
        service.save_plan(fields, [])
        tracked["loan"].is_paid_off = 1
        db_session.commit()
        refreshed = service.get_plan()["fields"]
        assert refreshed["num_loan_fields"] == "1"
        assert refreshed["debtInitialSum1"] == "10000"
        assert "debtSource1" not in refreshed

    def test_reset_returns_to_the_derived_plan(
        self, db_session: Session, tracked: dict
    ) -> None:
        """Resetting forgets the saved plan."""
        service = _service(db_session)
        service.save_plan({"balance": "1"}, [])
        plan = service.reset_plan()
        assert plan["saved"] is False
        assert plan["fields"]["balance"] == "51000"
