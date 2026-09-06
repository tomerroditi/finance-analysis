"""The four "base problems" the reference offers.

Two of them (`improve_cash`, `increase_risk`) **crash in the live reference**
with a `TypeError` and have evidently never run (notes/09). They are therefore
implemented from intent rather than cloned, and are marked as such — do not
present their output as parity with the reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from backend.services.fire.engine import SimulationResult, Simulator
from backend.services.fire.models import BaseProblem, Plan, PortfolioDesignation


@dataclass
class Goal:
    """One row of the reference's attainment checklist."""

    key: str
    label: str
    met: bool
    shortfall: float = 0.0


@dataclass
class SolveResult:
    problem: BaseProblem
    retire_index: int | None
    retire_age: float | None
    search_limit: int
    simulation: SimulationResult | None = None
    goals: list[Goal] = field(default_factory=list)
    cash_improvement: float | None = None
    """`improve_cash` only: the monthly improvement the plan needs."""
    return_increase_pct: float | None = None
    """`increase_risk` only: the extra return the plan needs."""
    inferred: bool = False
    """True when the reference's own implementation is broken, so our answer
    cannot be checked against it."""

    @property
    def succeeded(self) -> bool:
        return self.retire_index is not None and all(g.met for g in self.goals)


def search_limit(plan: Plan, today: date) -> int:
    """Number of candidate retirement months.

    Verified against the reference's own failure message, which quotes this
    bound: a 36.67-year-old with a max retirement age of 60 is told the search
    covered 280 months, and (60 - 36.67) * 12 = 280.
    """
    age_now = Simulator(plan).age_at(0, today)
    return int(round((plan.max_retire_age - age_now) * 12))


def evaluate_goals(plan: Plan, result: SimulationResult) -> list[Goal]:
    """The attainment checklist the reference prints alongside the verdict."""
    shortfall = sum(month.shortfall for month in result.months)
    goals = [
        Goal("living_expenses", "כיסוי הוצאות מחיה",
             met=shortfall <= 1e-6, shortfall=shortfall),
        Goal("bequest", "יעד הורשה", met=result.months[-1].net_worth >= -1e-6,
             shortfall=max(-result.months[-1].net_worth, 0.0)),
    ]
    final = result.months[-1].assets
    for index, portfolio in enumerate(plan.portfolios):
        if portfolio.goal <= 0 or portfolio.designation == PortfolioDesignation.WITHDRAW:
            continue
        reached = max(month.assets.get(f"portfolio{index}", 0.0) for month in result.months)
        goals.append(Goal(f"portfolio{index}",
                          portfolio.description or f"תיק {index + 1}",
                          met=reached >= portfolio.goal - 1e-6,
                          shortfall=max(portfolio.goal - reached, 0.0)))
    for who, fund in (("main", plan.pension), ("partner", plan.partner_pension)):
        if fund is not None:
            goals.append(Goal(f"pension_{who}", f"קרן פנסיה ({who})",
                              met=final.get("pension0", 0.0) >= -1e-6))
    return goals


def _feasible(plan: Plan, candidate: int, today: date) -> tuple[bool, SimulationResult]:
    result = Simulator(plan).run(retire_index=candidate, today=today)
    goals = evaluate_goals(plan, result)
    return all(g.met for g in goals), result


def solve(plan: Plan, today: date | None = None) -> SolveResult:
    """Dispatch on the plan's base problem."""
    today = today or date.today()
    if plan.base_problem == BaseProblem.RETIRE_ASAP:
        return solve_retire_asap(plan, today)
    if plan.base_problem == BaseProblem.RETIRE_AT_AGE:
        return solve_retire_at_age(plan, today)
    if plan.base_problem == BaseProblem.IMPROVE_CASH:
        return solve_improve_cash(plan, today)
    return solve_increase_risk(plan, today)


def solve_retire_asap(plan: Plan, today: date | None = None) -> SolveResult:
    """Earliest retirement month that meets every goal."""
    today = today or date.today()
    limit = search_limit(plan, today)
    simulator = Simulator(plan)

    # The earliest possible retirement is month 1: the reference reports the
    # *last working* month, and the earliest that can be is the current one.
    for candidate in range(1, max(limit, 1) + 1):
        ok, result = _feasible(plan, candidate, today)
        if ok:
            return SolveResult(
                problem=BaseProblem.RETIRE_ASAP,
                retire_index=candidate,
                retire_age=simulator.age_at(candidate - 1, today),
                search_limit=limit,
                simulation=result,
                goals=evaluate_goals(plan, result),
            )

    result = Simulator(plan).run(retire_index=max(limit, 0), today=today)
    return SolveResult(problem=BaseProblem.RETIRE_ASAP, retire_index=None,
                       retire_age=None, search_limit=limit, simulation=result,
                       goals=evaluate_goals(plan, result))


def solve_retire_at_age(plan: Plan, today: date | None = None) -> SolveResult:
    """Check-up: pin retirement to the requested age and report each goal."""
    today = today or date.today()
    simulator = Simulator(plan)
    target = plan.wanted_retire_age or plan.max_retire_age
    age_now = simulator.age_at(0, today)
    candidate = max(int(round((target - age_now) * 12)), 0)
    result = Simulator(plan).run(retire_index=candidate, today=today)
    return SolveResult(problem=BaseProblem.RETIRE_AT_AGE, retire_index=candidate,
                       retire_age=simulator.age_at(candidate - 1, today),
                       search_limit=search_limit(plan, today), simulation=result,
                       goals=evaluate_goals(plan, result))


def _bisect_smallest(feasible, low: float, high: float, steps: int = 40) -> float | None:
    """Smallest value in [low, high] for which `feasible` is true."""
    if not feasible(high):
        return None
    if feasible(low):
        return low
    for _ in range(steps):
        mid = (low + high) / 2
        if feasible(mid):
            high = mid
        else:
            low = mid
    return high


def solve_improve_cash(plan: Plan, today: date | None = None) -> SolveResult:
    """Smallest monthly cash-flow improvement that reaches the target age.

    INFERRED — the reference crashes on this mode (notes/09).
    """
    today = today or date.today()
    target = plan.wanted_retire_age or plan.max_retire_age
    age_now = Simulator(plan).age_at(0, today)
    candidate = max(int(round((target - age_now) * 12)), 0)

    def feasible(improvement: float) -> bool:
        return _feasible(replace(plan, monthly_cash_improvement=improvement),
                         candidate, today)[0]

    needed = _bisect_smallest(feasible, 0.0, plan.max_cash_improvement)
    trial = replace(plan, monthly_cash_improvement=needed or 0.0)
    result = Simulator(trial).run(retire_index=candidate, today=today)
    return SolveResult(problem=BaseProblem.IMPROVE_CASH,
                       retire_index=candidate if needed is not None else None,
                       retire_age=Simulator(plan).age_at(candidate - 1, today),
                       search_limit=search_limit(plan, today), simulation=result,
                       goals=evaluate_goals(trial, result),
                       cash_improvement=needed, inferred=True)


def solve_increase_risk(plan: Plan, today: date | None = None) -> SolveResult:
    """Smallest return increase that reaches the target age.

    INFERRED — the reference crashes on this mode (notes/09).
    """
    today = today or date.today()
    target = plan.wanted_retire_age or plan.max_retire_age
    age_now = Simulator(plan).age_at(0, today)
    candidate = max(int(round((target - age_now) * 12)), 0)

    def with_extra_return(extra: float) -> Plan:
        trial = replace(plan)
        trial.portfolios = [replace(p, annual_return_pct=p.annual_return_pct + extra)
                            for p in plan.portfolios]
        return trial

    def feasible(extra: float) -> bool:
        return _feasible(with_extra_return(extra), candidate, today)[0]

    needed = _bisect_smallest(feasible, 0.0, plan.max_risk_increase_pct)
    trial = with_extra_return(needed or 0.0)
    result = Simulator(trial).run(retire_index=candidate, today=today)
    return SolveResult(problem=BaseProblem.INCREASE_RISK,
                       retire_index=candidate if needed is not None else None,
                       retire_age=Simulator(plan).age_at(candidate - 1, today),
                       search_limit=search_limit(plan, today), simulation=result,
                       goals=evaluate_goals(trial, result),
                       return_increase_pct=needed, inferred=True)
