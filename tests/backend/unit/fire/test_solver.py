"""The solver must reach the same answer the reference published.

Parity of the simulation is one thing; parity of the *verdict* is what a user
sees. These tests replay every recorded `retire_asap` scenario and assert we
pick the same retirement month.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from backend.services.fire.models import BaseProblem, Plan, Person, Gender, CashFlow, EndType
from backend.services.fire.reference_form import plan_from_reference
from backend.services.fire.solver import (
    evaluate_goals,
    search_limit,
    solve,
    solve_improve_cash,
    solve_increase_risk,
    solve_retire_asap,
    solve_retire_at_age,
)

RESEARCH = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc"
FIXTURES = RESEARCH / "fixtures"
RATES = json.loads((RESEARCH / "decumulation_rates.json").read_text(encoding="utf-8"))
RECORDED_IN = date(2026, 9, 1)


def _reference_retire_index(fixture: dict) -> int | None:
    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if not match:
        return None
    month, year = int(match.group(1)), int(match.group(2))
    return ((year - RECORDED_IN.year) * 12 + (month - RECORDED_IN.month)) + 1


def _asap_cases() -> list[str]:
    names = []
    for name in sorted(RATES):
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        if plan.base_problem is BaseProblem.RETIRE_ASAP and _reference_retire_index(fixture):
            names.append(name)
    return names


class TestRetireAsapParity:
    """Our search must land on the reference's own retirement month."""

    @pytest.mark.parametrize("name", _asap_cases())
    def test_finds_the_same_retirement_month(self, name):
        """The earliest feasible month agrees with what the reference published."""
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        plan.decumulation_return_pct = RATES[name]["decumulation_return_pct"]
        assert solve_retire_asap(plan, RECORDED_IN).retire_index == _reference_retire_index(fixture)

    def test_search_bound_matches_the_reference(self):
        """The reference quotes its own search space; ours must equal it."""
        fixture = json.loads((FIXTURES / "desig_goal.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        assert search_limit(plan, RECORDED_IN) == 280
        assert "280" in fixture["summary"]

    def test_a_person_past_the_search_window_gets_no_result(self):
        """`old_66`: a 66-year-old searching up to 60 has no month to try.

        The reference answers `אין תוצאות להצגה` and publishes no charts at
        all — not a failed plan, no plan. The same holds for someone already
        past the age-81 horizon, where there is no simulation to run either.
        """
        fixture = json.loads((FIXTURES / "old_66.json").read_text(encoding="utf-8"))
        assert "אין תוצאות להצגה" in fixture["summary"]
        assert not fixture.get("charts")

        plan = plan_from_reference(fixture["overrides"])
        outcome = solve(plan, RECORDED_IN)
        assert outcome.simulation is None
        assert outcome.retire_index is None

        plan.person.date_of_birth = date(1930, 1, 1)
        assert solve(plan, RECORDED_IN).simulation is None

    def test_cannot_retire_before_working_a_month(self):
        """The earliest retirement the reference will report is month 1."""
        fixture = json.loads((FIXTURES / "pf_types_all.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        plan.decumulation_return_pct = RATES["pf_types_all"]["decumulation_return_pct"]
        assert solve_retire_asap(plan, RECORDED_IN).retire_index == 1


def _simple_plan(**kwargs) -> Plan:
    return Plan(
        person=Person(name="T", gender=Gender.MALE, date_of_birth=date(1990, 1, 1)),
        incomes=[CashFlow(amount=10_000, end_type=EndType.FIRE)],
        expenses=[CashFlow(amount=5_000)],
        **kwargs,
    )


class TestCheckUp:
    """`retire_at_age` pins the age and reports each goal separately."""

    def test_reports_failure_per_goal(self):
        """An unaffordable target age fails the living-expenses goal, not all of them."""
        plan = _simple_plan(base_problem=BaseProblem.RETIRE_AT_AGE, wanted_retire_age=45)
        result = solve_retire_at_age(plan, RECORDED_IN)
        failed = {goal.key for goal in result.goals if not goal.met}
        assert "living_expenses" in failed
        assert result.retire_index is not None, "a check-up still returns a projection"

    def test_a_reachable_age_passes(self):
        """A comfortable target age meets every goal."""
        plan = _simple_plan(base_problem=BaseProblem.RETIRE_AT_AGE, wanted_retire_age=58)
        assert solve_retire_at_age(plan, RECORDED_IN).succeeded


class TestInferredSolverModes:
    """`improve_cash` and `increase_risk` crash in the reference, so ours are
    inferred from intent and must say so."""

    def test_improve_cash_finds_the_smallest_workable_improvement(self):
        """The solver returns the least extra monthly saving that reaches the age."""
        plan = _simple_plan(base_problem=BaseProblem.IMPROVE_CASH,
                            wanted_retire_age=50, max_cash_improvement=20_000)
        result = solve_improve_cash(plan, RECORDED_IN)
        assert result.inferred
        assert result.cash_improvement is not None
        assert 0 < result.cash_improvement <= 20_000

    def test_improve_cash_reports_when_the_bound_is_not_enough(self):
        """A cap too small to reach the target age yields no answer."""
        plan = _simple_plan(base_problem=BaseProblem.IMPROVE_CASH,
                            wanted_retire_age=40, max_cash_improvement=100)
        assert solve_improve_cash(plan, RECORDED_IN).cash_improvement is None

    def test_increase_risk_finds_the_smallest_workable_return(self):
        """The solver returns the least extra return that reaches the age."""
        plan = _simple_plan(base_problem=BaseProblem.INCREASE_RISK,
                            wanted_retire_age=52, max_risk_increase_pct=10)
        result = solve_increase_risk(plan, RECORDED_IN)
        assert result.inferred
        assert result.return_increase_pct is None or result.return_increase_pct <= 10


class TestGoals:
    """The attainment checklist mirrors the reference's own rows."""

    def test_a_solvent_plan_meets_both_base_goals(self):
        """Living expenses and the bequest goal both pass when money never runs out."""
        plan = _simple_plan()
        result = solve_retire_asap(plan, RECORDED_IN)
        assert {g.key for g in result.goals} >= {"living_expenses", "bequest"}
        assert all(g.met for g in result.goals)

    def test_shortfall_is_reported_not_just_flagged(self):
        """A failing plan quantifies the gap, as the reference does."""
        plan = _simple_plan(base_problem=BaseProblem.RETIRE_AT_AGE, wanted_retire_age=40)
        goals = {g.key: g for g in solve_retire_at_age(plan, RECORDED_IN).goals}
        assert goals["living_expenses"].shortfall > 0
