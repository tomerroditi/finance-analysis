"""State pension, and the bridge the decumulation surface is read on.

Both rules here were recovered from single, decisive fixtures — see
``research/zeke_retire_calc/notes/15-the-bridge.md``.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.fire import national_insurance
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


class TestDecumulationBridge:
    """Which wait the decumulation surface is read on."""

    def test_claiming_the_pension_early_cuts_the_return(self):
        """A pension drawn from 60 shortens the bridge, so less growth is assumed."""
        early = Simulator(_plan(PensionTactic.ALL_FROM_60))
        late = Simulator(_plan(PensionTactic.ALL_FROM_STATUTORY))
        early.run(retire_index=120, today=TODAY)
        late.run(retire_index=120, today=TODAY)
        assert early._decumulation_return(120) < late._decumulation_return(120)

    def test_a_split_claim_lands_between_the_two(self):
        """Claiming the recognised share at 60 is neither one wait nor the other."""
        rates = {}
        for tactic in PensionTactic:
            simulator = Simulator(_plan(tactic))
            simulator.run(retire_index=120, today=TODAY)
            rates[tactic] = simulator._decumulation_return(120)
        assert (rates[PensionTactic.ALL_FROM_60]
                < rates[PensionTactic.MUKERET_60_ZAKA_STATUTORY]
                < rates[PensionTactic.ALL_FROM_STATUTORY])

    def test_a_plan_with_no_pension_waits_for_the_statutory_age(self):
        """With nothing claimed early the bridge is the plain statutory one."""
        plan = _plan(PensionTactic.ALL_FROM_STATUTORY)
        plan.pension = None
        simulator = Simulator(plan)
        simulator.run(retire_index=120, today=TODAY)
        from backend.services.fire.decumulation import decumulation_return_pct
        assert simulator._decumulation_return(120) == pytest.approx(
            decumulation_return_pct(85, simulator._retire_age_cache(120), 67))

    def test_the_probe_pass_is_skipped_when_nothing_is_claimed_early(self):
        """No early claim means no need to run the simulation twice."""
        assert not Simulator(_plan(PensionTactic.ALL_FROM_STATUTORY))._needs_stream_pass()
        assert Simulator(_plan(PensionTactic.ALL_FROM_60))._needs_stream_pass()

    def test_the_blend_reproduces_the_one_recorded_two_bridge_run(self):
        """`pn_annuity_6067` is the only run that genuinely reads two bridges.

        Its shorter bridge is 11 years, deep in the stretch where the surface
        has collapsed to 0.0002, so the blend reduces to the longer stream's
        weight times the surface at 18 years. Solving the rule for that one
        value gives 1.3462 — and with it the rule returns the rate the run was
        measured at, exactly. What is left over is the surface's interpolation
        across a gap it has no cell in, not the weighting rule (notes/15).
        """
        from backend.services.fire.decumulation import _for_rule

        short_pay, long_pay = 1604.15, 4246.21
        measured = 0.97710461
        implied = ((measured * (short_pay + long_pay)
                    - short_pay * _for_rule(85.0, 11.0)) / long_pay)
        assert implied == pytest.approx(1.3462, abs=5e-4)
        assert _for_rule(85.0, 11.0) < 0.01, "the short bridge must be collapsed"
        assert _for_rule(85.0, 18.0) == pytest.approx(implied, rel=0.01), (
            "the interpolated cell is within a percent of what the run measures; "
            "a probe of the reference at bridge 18.0 would close the rest")
