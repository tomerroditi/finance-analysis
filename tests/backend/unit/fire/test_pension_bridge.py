"""State pension, and the bridge the decumulation surface is read on.

Every rule here was recovered from reference probes — see
``research/zeke_retire_calc/notes/18-bridge-rule.md``.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.fire import national_insurance
from backend.services.fire.bridge import bridge_months, window_share
from backend.services.fire.israeli_tax import monthly_income_tax
from backend.services.fire.pension import contributions_on
from backend.services.fire.engine import Simulator
from backend.services.fire.models import (
    CashFlow,
    EndType,
    Gender,
    Pension,
    PensionTactic,
    Person,
    Plan,
    Portfolio,
    PortfolioDesignation,
)

TODAY = date(2026, 9, 1)


def _plan(tactic: PensionTactic) -> Plan:
    """A single retiree with one withdrawal portfolio and one pension fund."""
    return Plan(
        person=Person(name="T", gender=Gender.MALE, date_of_birth=date(1990, 1, 1)),
        cash_balance=0.0,
        incomes=[CashFlow(amount=10_000, end_type=EndType.FIRE)],
        expenses=[CashFlow(amount=5_000, end_type=EndType.FOREVER)],
        portfolios=[Portfolio(balance=1_000_000, annual_return_pct=5.0,
                              annual_fee_pct=0.1,
                              designation=PortfolioDesignation.WITHDRAW)],
        pension=Pension(balance=1_200_000, tactic=tactic, mukeret_pct=30),
    )


class TestStatePension:
    """Bituach Leumi old-age pension as the reference pays it."""

    def test_nothing_before_the_claim_age(self):
        """The pension starts the month *after* the statutory birthday."""
        person = Person(gender=Gender.MALE)
        assert national_insurance.monthly_amount(person, 67.0) == 0.0
        assert national_insurance.monthly_amount(person, 67.09) == 2757.0

    def test_women_claim_two_years_earlier(self):
        """The reference uses a flat 65 for women, 67 for men."""
        woman = Person(gender=Gender.FEMALE)
        assert national_insurance.monthly_amount(woman, 65.09) == 2757.0

    def test_steps_up_at_eighty(self):
        """From the month after the 80th birthday the amount rises."""
        person = Person(gender=Gender.MALE)
        assert national_insurance.monthly_amount(person, 80.09) == 2911.5

    def test_a_spouse_below_claim_age_adds_an_increment(self):
        """A wife eligible at 65 draws for two more people until he turns 67."""
        wife = Person(gender=Gender.FEMALE)
        husband = Person(gender=Gender.MALE)
        assert national_insurance.monthly_amount(wife, 65.5, husband, 65.5) == 4143.0

    def test_the_increment_stops_once_both_are_eligible(self):
        """Two eligible spouses each draw their own pension and nothing more."""
        wife = Person(gender=Gender.FEMALE)
        husband = Person(gender=Gender.MALE)
        assert national_insurance.monthly_amount(wife, 67.5, husband, 67.5) == 2757.0
        assert national_insurance.monthly_amount(husband, 67.5, wife, 67.5) == 2757.0


class TestBridgeMonths:
    """Which horizon the decumulation surface is read at (bridge.py).

    Month numbers count from today. The cases are the probes that established
    each rule, for a man born January 1990 recorded in September 2026: he
    turns 60 in month 280 and 67 in month 364.
    """

    def test_no_claim_at_60_waits_for_the_statutory_age(self):
        """Tactic 67, retiring at 45 (last pay in month 100): 22 years."""
        assert bridge_months(100, 280, 364, claims_at_60=False, coverage=0.4) == 264

    def test_an_empty_pension_claimed_at_60_changes_nothing_before_60(self):
        """With nothing paid at 60 the bridge is still the statutory wait."""
        assert bridge_months(100, 280, 364, claims_at_60=True, coverage=0.0) == 264

    def test_full_coverage_ends_the_bridge_at_60(self):
        """A pension that pays all the spending from 60 needs no longer bridge."""
        assert bridge_months(100, 280, 364, claims_at_60=True, coverage=1.07) == 180

    def test_partial_coverage_ends_it_inside_the_window(self):
        """`gb_t6067_0k`: a net x of 0.3072 ends the bridge at 65.73, not 65.08."""
        months = bridge_months(100, 280, 364, claims_at_60=True, coverage=0.307196)
        assert 100 + months == pytest.approx(65.7325 * 12 - 440, abs=0.05)

    def test_the_window_share_is_about_half_the_coverage_when_small(self):
        """`y(x)` starts near x/2 and reaches ~0.91 just short of full coverage."""
        assert window_share(0.02048) == pytest.approx(0.010346, abs=2e-4)
        assert window_share(0.952307) == pytest.approx(0.908956, abs=2e-4)
        assert window_share(1.0) == 1.0

    def test_a_claim_already_behind_contributes_its_index_from_today(self):
        """`spt_a63_t60_0k`: retiring at 63 reads 23.4 years plus the 4 left to 67."""
        assert bridge_months(316, 280, 364, claims_at_60=True, coverage=0.0) == 329

    def test_past_the_statutory_age_the_whole_window_counts_again(self):
        """`spt_a68_t60_600k`: retiring at 68 with a net x of 0.512 reads 336 months."""
        months = bridge_months(376, 280, 364, claims_at_60=True, coverage=0.511992)
        assert months == pytest.approx(336.1, abs=0.2)

    def test_a_statutory_claim_behind_the_retirement_is_its_index_plus_one(self):
        """`spt_a68_t67_0k`: tactic 67, retiring at 68 — month 365."""
        assert bridge_months(376, 280, 364, claims_at_60=False, coverage=0.0) == 365


class TestCoverage:
    """What the engine counts as pension and as spending for the bridge."""

    def test_the_pension_counts_net_of_what_it_pays_before_67(self):
        """`cx1_029`: 9,718 gross at 60 counts as 8,887 after insurance and tax."""
        plan = _plan(PensionTactic.ALL_FROM_60)
        plan.pension = Pension(balance=2_180_000, tactic=PensionTactic.ALL_FROM_60,
                               mukeret_pct=20, monthly_deposit=0, annual_return_pct=0,
                               fee_on_balance_pct=0, fee_on_deposit_pct=0)
        gross = 2_180_000 / 224.41731
        net = Simulator(plan)._coverage(101, TODAY) * 5_000
        assert gross - net == pytest.approx(
            contributions_on(gross) + monthly_income_tax(gross * 0.8), abs=0.01)

    def _coverage(self, **changes) -> float:
        plan = _plan(PensionTactic.MUKERET_60_ZAKA_STATUTORY)
        plan.pension = Pension(balance=1_200_000, tactic=plan.pension.tactic,
                               mukeret_pct=30, monthly_deposit=0, annual_return_pct=0,
                               fee_on_balance_pct=0, fee_on_deposit_pct=0)
        for key, value in changes.items():
            setattr(plan, key, value)
        return Simulator(plan)._coverage(101, TODAY)

    def test_only_the_share_claimed_at_60_counts(self):
        """The recognised 30% at 60, net of 4.25% national insurance, over 5,000."""
        assert self._coverage() == pytest.approx(0.307196, abs=1e-5)

    def test_spending_that_ends_at_60_does_not_count(self):
        """`be_exp_end60`: only the rows still running after 60 are carried."""
        expenses = [CashFlow(amount=3_000), CashFlow(amount=2_000, end_type=EndType.AGE_60)]
        assert self._coverage(expenses=expenses) == pytest.approx(0.511992, abs=1e-5)

    def test_other_income_offsets_the_spending(self):
        """`be_inc_rent`: a 1,000 rent leaves 4,000 for the pension to cover."""
        incomes = [CashFlow(amount=10_000, end_type=EndType.FIRE), CashFlow(amount=1_000)]
        assert self._coverage(incomes=incomes) == pytest.approx(0.383995, abs=1e-5)

    def test_an_annual_rise_is_ignored(self):
        """`be_exp_rise`: a 1% rise reads exactly as the flat 5,000 does."""
        expenses = [CashFlow(amount=5_000, annual_rise_pct=1.0)]
        assert self._coverage(expenses=expenses) == pytest.approx(0.307196, abs=1e-5)
