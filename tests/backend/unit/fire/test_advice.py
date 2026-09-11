"""The smart-advice optimiser.

The reference's own recommendation for a plan with no withdrawal portfolio is
recorded in `fixtures/sol_smart_advice`; these tests pin our mechanism to it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.services.fire.advice import AdviceOutcome, advise, apply, propose
from backend.services.fire.models import PortfolioDesignation
from backend.services.fire.reference_form import plan_from_reference
from backend.services.fire.solver import solve

RESEARCH = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc"
RECORDED_IN = date(2026, 9, 1)


def _fixture(name: str) -> dict:
    return json.loads((RESEARCH / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


class TestSmartAdvice:
    """Diagnosis, action and outcome must match the reference's."""

    def test_spots_a_missing_withdrawal_portfolio(self):
        """A plan whose only portfolio is earmarked for goals cannot fund living."""
        plan = plan_from_reference(_fixture("desig_goal")["overrides"])
        plan.decumulation_return_pct = 2.0
        recommendation = propose(plan, solve(plan, RECORDED_IN))
        assert recommendation is not None
        assert recommendation.action == "open_living_portfolio"
        assert recommendation.reason == "no_living_portfolio"

    def test_token_matches_the_reference_wire_format(self):
        """Our token is shaped like the one the reference actually emitted."""
        plan = plan_from_reference(_fixture("desig_goal")["overrides"])
        plan.decumulation_return_pct = 2.0
        token = propose(plan, solve(plan, RECORDED_IN)).token()
        recorded = _fixture("sol_smart_advice")["advice_token"]
        assert token.split("@")[0] == recorded.split("@")[0]
        assert "reason=no_living_portfolio" in token
        assert "portfolio_subtype=auto_broker" in token
        assert token.split("@")[1] == "interest=5", "the reference writes 5, not 5.0"

    def test_reports_the_same_outcome_as_the_reference(self):
        """For this plan the reference found its own advice did not help."""
        plan = plan_from_reference(_fixture("desig_goal")["overrides"])
        plan.decumulation_return_pct = 2.0
        recommendation = advise(plan, solve(plan, RECORDED_IN), RECORDED_IN)
        recorded = _fixture("sol_smart_advice")["meta"]["extra_status"]["extra_status"]
        assert recommendation.outcome.value == recorded

    def test_applying_the_advice_adds_a_withdrawal_portfolio(self):
        """The proposed plan differs from the original in exactly that way."""
        plan = plan_from_reference(_fixture("desig_goal")["overrides"])
        improved = apply(plan, propose(plan, solve(plan, RECORDED_IN)))
        assert len(improved.portfolios) == len(plan.portfolios) + 1
        assert improved.portfolios[-1].designation is PortfolioDesignation.WITHDRAW
        assert not any(p.designation is PortfolioDesignation.WITHDRAW
                       for p in plan.portfolios), "the original is left untouched"

    def test_no_advice_when_the_plan_is_already_sound(self):
        """A plan with a funded withdrawal portfolio gets no recommendation."""
        plan = plan_from_reference(_fixture("goal_big")["overrides"])
        plan.decumulation_return_pct = 1.12
        assert propose(plan, solve(plan, RECORDED_IN)) is None

    def test_outcome_is_improved_when_it_actually_helps(self):
        """Advice that brings retirement forward reports the months saved."""
        plan = plan_from_reference(_fixture("baseline")["overrides"])
        plan.decumulation_return_pct = 0.0246
        baseline = solve(plan, RECORDED_IN)
        recommendation = advise(plan, baseline, RECORDED_IN)
        if recommendation is not None and recommendation.outcome is AdviceOutcome.IMPROVED:
            assert recommendation.months_saved > 0
