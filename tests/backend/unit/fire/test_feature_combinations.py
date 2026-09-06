"""Scenarios that wire many features together at once.

The parity tests cover each rule against a recorded run, but each recorded run
exercises a handful of features. These are the combinations nobody recorded: a
couple whose pensions are claimed at different ages, a study fund drawn ahead of
a portfolio that is itself selling FIFO lots to pay a mortgage, a gemel
annuitising into a national-insurance base, one-off flows landing in the same
month as a severance redemption.

They cannot assert against the reference — there are no fixtures for them — so
they assert **identities** instead, which is what catches a feature that is
right alone and wrong in company:

* the cash-flow decomposition closes every month (a shekel that appears without
  a source, or is spent without a destination, breaks it);
* net worth is assets less debt, and no series ever goes non-finite;
* the balances that must not go negative do not, and the ones with a floor stop
  at it.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from backend.services.fire.engine import HORIZON_AGE, Simulator
from backend.services.fire.models import (
    BaseProblem,
    CashFlow,
    EndType,
    Gender,
    KerenHishtalmut,
    KerenType,
    Loan,
    LoanType,
    LotMethod,
    Pension,
    PensionTactic,
    Person,
    Plan,
    Portfolio,
    PortfolioDesignation,
    PortfolioType,
    RealEstate,
    StartType,
)
from backend.services.fire.solver import solve

TODAY = date(2026, 9, 1)


def everything_plan(**overrides) -> Plan:
    """A couple using every instrument the reference offers, at once."""
    plan = Plan(
        person=Person(name="T", gender=Gender.MALE, date_of_birth=date(1985, 3, 1)),
        partner=Person(name="S", gender=Gender.FEMALE, date_of_birth=date(1988, 11, 1)),
        cash_balance=180_000,
        cash_buffer=40_000,
        credit_limit=25_000,
        incomes=[
            CashFlow(amount=48_000, end_type=EndType.FIRE, annual_rise_pct=1.5),
            CashFlow(amount=3_000, start_type=StartType.FROM_DATE,
                     start_date=date(2030, 1, 1), end_type=EndType.FOREVER),
            CashFlow(amount=250_000, start_type=StartType.ONE_TIME,
                     start_date=date(2034, 6, 1)),
        ],
        expenses=[
            CashFlow(amount=22_000, end_type=EndType.FOREVER, annual_rise_pct=0.5),
            CashFlow(amount=4_500, end_type=EndType.AGE_60),
            CashFlow(amount=90_000, start_type=StartType.ONE_TIME,
                     start_date=date(2034, 6, 1)),
            CashFlow(amount=6_000, start_type=StartType.FIRE, end_type=EndType.TO_DATE,
                     end_date=date(2055, 1, 1)),
        ],
        portfolios=[
            Portfolio(balance=900_000, profit_fraction_pct=55, lot_method=LotMethod.FIFO,
                      annual_return_pct=6.5, goal=6_000_000, description="Broker"),
            Portfolio(balance=400_000, kind=PortfolioType.IBKR, profit_fraction_pct=80,
                      lot_method=LotMethod.LIFO, goal=3_000_000, description="IBKR"),
            Portfolio(balance=250_000, kind=PortfolioType.GEMEL,
                      designation=PortfolioDesignation.MUKERET_MAIN,
                      goal=2_000_000, description="Gemel-T"),
            Portfolio(balance=150_000, kind=PortfolioType.GEMEL,
                      designation=PortfolioDesignation.MUKERET_PARTNER,
                      goal=2_000_000, description="Gemel-S"),
            Portfolio(balance=300_000, kind=PortfolioType.POLISA,
                      designation=PortfolioDesignation.GOAL, goal=1_500_000,
                      description="Polisa"),
            Portfolio(balance=120_000, kind=PortfolioType.KASPIT, goal=800_000,
                      monthly_deposit_cap=4_000, description="Kaspit"),
        ],
        pension=Pension(balance=1_100_000, monthly_deposit=4_200,
                        tactic=PensionTactic.MUKERET_60_ZAKA_STATUTORY,
                        withdraw_severance=True, work_start_year=2008),
        partner_pension=Pension(balance=700_000, monthly_deposit=3_100,
                                tactic=PensionTactic.ALL_FROM_60, mukeret_pct=45),
        kranot_hishtalmut=[
            KerenHishtalmut(balance=260_000, monthly_deposit=2_400),
            KerenHishtalmut(balance=90_000, monthly_deposit=0, kind=KerenType.IRA,
                            annual_fee_pct=0.3),
        ],
        loans=[
            Loan(start_date=date(2024, 5, 1), initial_sum=900_000, term_years=25,
                 annual_interest_pct=4.2),
            Loan(start_date=date(2031, 2, 1), initial_sum=200_000, term_years=8,
                 annual_interest_pct=6.0, kind=LoanType.BALOON),
        ],
        real_estate=[RealEstate(value=2_400_000, annual_rise_pct=1.2)],
        max_retire_age=62,
        retire_rule_confidence=90,
        draw_keren_before_portfolio=True,
    )
    for key, value in overrides.items():
        setattr(plan, key, value)
    return plan


def assert_sound(result, plan) -> None:
    """Every identity the engine must hold, whatever the scenario."""
    assert result.months, "a run must produce months"
    assert result.months[-1].age == pytest.approx(HORIZON_AGE)

    for record in result.months:
        assert sum(record.incomes.values()) == pytest.approx(
            sum(record.expenses.values()), abs=1e-6), (
            f"month {record.index} does not balance")
        assert all(math.isfinite(v) for v in record.assets.values())
        assert math.isfinite(record.net_worth) and math.isfinite(record.liabilities)
        assert record.net_worth == pytest.approx(
            sum(record.assets.values()) - record.liabilities)
        assert record.cash >= -plan.credit_limit - 1e-6, (
            f"month {record.index} overdrew past the credit limit")
        for key, value in record.assets.items():
            if key != "cash":
                assert value >= -1e-6, f"{key} went negative in month {record.index}"
        assert all(v >= -1e-6 for v in record.incomes.values())
        assert all(v >= -1e-6 for v in record.expenses.values())


@pytest.fixture(scope="module")
def run():
    """One run of the everything-plan, shared by the identity assertions."""
    plan = everything_plan()
    return plan, Simulator(plan).run(retire_index=200, today=TODAY)


class TestEverythingAtOnce:
    """One plan using every instrument, asserted on identities."""

    def test_the_month_closes_every_month(self, run):
        """Nothing appears from nowhere and nothing is spent into nowhere."""
        plan, result = run
        assert_sound(result, plan)

    def test_every_instrument_actually_participates(self, run):
        """A combination test proves nothing if half the plan sits idle."""
        _, result = run
        seen = set()
        for record in result.months:
            seen.update(k for k, v in record.incomes.items() if v)
            seen.update(k for k, v in record.expenses.items() if v)
        for key in ("work", "one_time", "cash", "state_pension", "state_pension_partner",
                    "recognised", "entitling", "recognised_partner", "entitling_partner",
                    "living", "loans", "unplanned"):
            assert key in seen, f"{key} never moved"
        assert any(k.startswith("portfolio") for k in seen)
        assert any(k.startswith("deposit_portfolio") for k in seen)
        assert any(k.startswith("gemel") for k in seen)
        assert any(k.startswith("keren") for k in seen)
        assert any(k.startswith("capital_gains_tax") for k in seen)
        assert any(k.startswith("national_insurance") for k in seen)

    def test_the_gemel_ceiling_holds_with_five_other_accounts_competing(self, run):
        """The statutory monthly cap binds per account, not per plan."""
        _, result = run
        ceiling = 76_449 / 12 + 1e-6
        for record in result.months:
            for key, value in record.expenses.items():
                if key.startswith("deposit_portfolio") and key.endswith(("2", "3")):
                    assert value <= ceiling

    def test_goal_portfolios_stop_at_their_goal(self, run):
        """A deposit never pushes an account past the goal it was given."""
        plan, result = run
        for record in result.months:
            for index, portfolio in enumerate(plan.portfolios):
                if not portfolio.goal:
                    continue
                deposit = record.expenses.get(f"deposit_portfolio{index}", 0.0)
                if deposit:
                    assert record.assets[f"portfolio{index}"] <= portfolio.goal * 1.5

    def test_severance_is_paid_once_and_charted_as_one_off_income(self, run):
        """The redemption lands in the first retired month, once, as one-off pay."""
        plan, result = run
        months = [m for m in result.months if m.incomes.get("one_time", 0) > 100_000]
        assert len(months) == 2, "the typed one-off and the severance, one month each"
        assert result.retire_index in [m.index for m in months]

    def test_a_womans_pension_arrives_before_a_mans(self, run):
        """Statutory ages differ, so the couple's state pensions start apart."""
        _, result = run
        hers = next(m.index for m in result.months if m.incomes.get("state_pension_partner"))
        his = next(m.index for m in result.months if m.incomes.get("state_pension"))
        assert hers != his
        # While only one of them is eligible, that one draws the spouse increment.
        assert result.months[min(hers, his)].incomes[
            "state_pension_partner" if hers < his else "state_pension"] == 4143.0


class TestCombinationsThatCouldInteract:
    """Pairs of features that share a code path, exercised together."""

    def test_a_study_fund_drawn_first_still_leaves_the_portfolio_taxed(self):
        """`prati_hishtalmut_order` changes the order, not the tax on the sale."""
        results = {}
        for first in (False, True):
            plan = everything_plan(draw_keren_before_portfolio=first)
            results[first] = Simulator(plan).run(retire_index=180, today=TODAY)
            assert_sound(results[first], plan)
        keren_first = sum(m.incomes.get("keren0", 0.0) for m in results[True].months[:400])
        keren_last = sum(m.incomes.get("keren0", 0.0) for m in results[False].months[:400])
        assert keren_first > keren_last, "the study fund should be emptied sooner"

    @pytest.mark.parametrize("method", list(LotMethod))
    def test_every_lot_method_survives_the_full_plan(self, method):
        """FIFO, LIFO and the flat basis all close the month, every month."""
        plan = everything_plan()
        for portfolio in plan.portfolios:
            portfolio.lot_method = method
        assert_sound(Simulator(plan).run(retire_index=190, today=TODAY), plan)

    @pytest.mark.parametrize("tactic", list(PensionTactic))
    def test_every_pension_tactic_survives_a_couple_with_a_gemel(self, tactic):
        """Both pensions claimed the same way, alongside two annuitising gemels."""
        plan = everything_plan()
        plan.pension.tactic = tactic
        plan.partner_pension.tactic = tactic
        result = Simulator(plan).run(retire_index=190, today=TODAY)
        assert_sound(result, plan)

    def test_retiring_after_sixty_still_closes(self):
        """The shifted branch of the decumulation surface, with everything on."""
        plan = everything_plan()
        assert_sound(Simulator(plan).run(retire_index=430, today=TODAY), plan)

    def test_a_plan_that_cannot_pay_records_the_gap_rather_than_inventing_money(self):
        """When every bucket is empty the shortfall is charted, not borrowed."""
        plan = everything_plan(cash_balance=0, cash_buffer=0, credit_limit=0,
                               portfolios=[], kranot_hishtalmut=[],
                               pension=None, partner_pension=None)
        result = Simulator(plan).run(retire_index=12, today=TODAY)
        assert_sound(result, plan)
        assert not result.solvent
        assert any(m.incomes.get("shortfall") for m in result.months)

    def test_a_zero_return_portfolio_moves_only_by_what_is_routed_through_it(self):
        """With no return and no fee, every balance is the routing arithmetic.

        `min(surface, the user's return)` must not invent growth after
        retirement — and each month's balance must be the previous one plus what
        the deposit rows say went in, less what the withdrawal rows say came
        out, to the agora. That ties the two charts to the balances.
        """
        plan = everything_plan()
        for portfolio in plan.portfolios:
            portfolio.annual_return_pct = 0.0
            portfolio.annual_fee_pct = 0.0
        result = Simulator(plan).run(retire_index=200, today=TODAY)
        assert_sound(result, plan)

        annuitising = {index for index, p in enumerate(plan.portfolios)
                       if p.designation in (PortfolioDesignation.MUKERET_MAIN,
                                            PortfolioDesignation.MUKERET_PARTNER)}
        for index, portfolio in enumerate(plan.portfolios):
            if index in annuitising:
                continue
            previous = portfolio.balance
            for record in result.months:
                expected = (previous
                            + record.expenses.get(f"deposit_portfolio{index}", 0.0)
                            - record.incomes.get(f"portfolio{index}", 0.0))
                assert record.assets[f"portfolio{index}"] == pytest.approx(
                    expected, abs=1e-6), (
                    f"portfolio {index} moved unaccountably in month {record.index}")
                previous = record.assets[f"portfolio{index}"]

    def test_the_horizon_holds_for_a_person_who_is_nearly_out_of_it(self):
        """A 79-year-old still gets a well-formed, closing run."""
        plan = everything_plan(person=Person(name="T", gender=Gender.MALE,
                                             date_of_birth=date(1947, 4, 1)),
                               partner=None, partner_pension=None)
        for portfolio in plan.portfolios:
            portfolio.designation = PortfolioDesignation.WITHDRAW
        result = Simulator(plan).run(retire_index=1, today=TODAY)
        assert_sound(result, plan)
        assert len(result.months) < 30


class TestSolverOnACombinedPlan:
    """The solver has to cope with the same plan the simulator does."""

    @pytest.mark.parametrize("problem", [BaseProblem.RETIRE_ASAP, BaseProblem.RETIRE_AT_AGE])
    def test_it_returns_a_month_whose_run_closes(self, problem):
        """Whatever month it picks, that month's simulation must be sound."""
        plan = everything_plan(base_problem=problem, wanted_retire_age=58)
        outcome = solve(plan, today=TODAY)
        assert outcome.simulation is not None
        assert_sound(outcome.simulation, plan)
        if outcome.simulation.solvent:
            assert 0 <= outcome.simulation.retire_index < len(outcome.simulation.months)


class TestHostileInputs:
    """Edge values that a form can produce and a model can trip over."""

    @pytest.mark.parametrize("mutate,label", [
        (lambda p: [setattr(x, "profit_fraction_pct", 100) for x in p.portfolios],
         "every portfolio is pure profit"),
        (lambda p: [setattr(x, "profit_fraction_pct", 0) for x in p.portfolios],
         "every portfolio is pure basis"),
        (lambda p: [setattr(x, "annual_return_pct", -4) for x in p.portfolios],
         "portfolios that lose money"),
        (lambda p: [setattr(x, "annual_fee_pct", 100) for x in p.portfolios],
         "a fee that takes everything"),
        (lambda p: setattr(p, "incomes", []), "no income at all"),
        (lambda p: setattr(p, "expenses", []), "no spending at all"),
        (lambda p: setattr(p, "credit_limit", 5_000_000), "a vast overdraft"),
        (lambda p: setattr(p, "cash_buffer", 10_000_000), "a buffer nobody can fill"),
        (lambda p: setattr(p, "loans", [Loan(start_date=date(2090, 1, 1),
                                             initial_sum=500_000, term_years=10)]),
         "a loan that starts past the horizon"),
        (lambda p: setattr(p, "kranot_hishtalmut",
                           [KerenHishtalmut(balance=50_000, end_type=EndType.TO_DATE,
                                            end_date=date(2020, 1, 1))]),
         "a study fund whose deposits ended long ago"),
        (lambda p: setattr(p, "real_estate", [RealEstate(value=9_000_000,
                                                         annual_rise_pct=-3)]),
         "property losing value"),
        (lambda p: setattr(p, "portfolios", []), "nothing invested"),
    ])
    def test_the_run_still_closes(self, mutate, label):
        """Whatever the input, the month balances and nothing goes non-finite."""
        plan = everything_plan()
        mutate(plan)
        assert_sound(Simulator(plan).run(retire_index=150, today=TODAY), plan)

    @pytest.mark.parametrize("method", [LotMethod.FIFO, LotMethod.LIFO])
    def test_a_portfolio_that_does_not_grow_still_sells_lots(self, method):
        """No growth means no synthetic history to manufacture.

        The lot model ages equal-basis purchases to reach the stated profit
        fraction; at a growth factor of exactly 1 there is nothing to age, and
        the search for a lot count used to divide by zero.
        """
        plan = everything_plan()
        for portfolio in plan.portfolios:
            portfolio.lot_method = method
            portfolio.annual_return_pct = 0.0
            portfolio.annual_fee_pct = 0.0
            portfolio.profit_fraction_pct = 60
        result = Simulator(plan).run(retire_index=150, today=TODAY)
        assert_sound(result, plan)
        assert any(m.expenses.get("capital_gains_tax0") for m in result.months), (
            "a 60%-profit portfolio must still pay tax when it is sold")

    def test_retiring_beyond_the_horizon_is_a_working_life(self):
        """A retirement month past age 81 simply never arrives."""
        plan = everything_plan()
        result = Simulator(plan).run(retire_index=10 ** 9, today=TODAY)
        assert_sound(result, plan)
        assert all(m.incomes.get("work") for m in result.months[:-1])
