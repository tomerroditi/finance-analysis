"""The "smart advice" optimiser.

The reference runs the plan, spots a structural gap, and re-runs with that gap
closed. Its recommendation travels as a token like

```
open_living_portfolio@interest=5@reason=no_living_portfolio
  @portfolio_deposit=None@portfolio_subtype=auto_broker,missing_piece,2129420.8
```

— an action, its parameters, the reason it fired, and the size of the shortfall
(notes/09). The outcome is reported as one of three states.

We reproduce the mechanism. We do not reproduce the referral links the
reference attaches to its recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum

from backend.services.fire.models import (
    Plan,
    Portfolio,
    PortfolioDesignation,
    PortfolioType,
)
from backend.services.fire.solver import SolveResult, solve


class AdviceOutcome(str, Enum):
    NOT_DONE = "not_done"
    NOT_BENEFICIAL = "success_but_extra_not_beneficial"
    IMPROVED = "improved_amazingly"


@dataclass
class Recommendation:
    """One proposed change, and what it would buy."""

    action: str
    reason: str
    parameters: dict[str, object] = field(default_factory=dict)
    missing_piece: float = 0.0
    outcome: AdviceOutcome = AdviceOutcome.NOT_DONE
    months_saved: int = 0
    improved: SolveResult | None = None

    def token(self) -> str:
        """The reference's own wire format, reproduced for comparability.

        It orders the fields action, first parameter, reason, then the rest —
        e.g. `open_living_portfolio@interest=5@reason=...@portfolio_deposit=None`.
        """
        items = [f"{k}={_render(v)}" for k, v in self.parameters.items()]
        parts = [self.action, *items[:1], f"reason={self.reason}", *items[1:]]
        return "@".join(parts) + f",missing_piece,{self.missing_piece}"


def _render(value: object) -> str:
    """Format a parameter the way the reference does (5, not 5.0)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


DEFAULT_ADVISED_RETURN = 5.0
"""Return the reference assumes for a portfolio it suggests opening."""


def _shortfall(result: SolveResult) -> float:
    return sum(goal.shortfall for goal in result.goals)


def _has_withdrawal_portfolio(plan: Plan) -> bool:
    return any(p.designation == PortfolioDesignation.WITHDRAW for p in plan.portfolios)


def _idle_surplus(plan: Plan) -> bool:
    """Surplus that piles up in cash because no portfolio will accept it."""
    return bool(plan.portfolios) and all(
        p.goal <= 0 for p in plan.portfolios) and not plan.cash_buffer


def propose(plan: Plan, baseline: SolveResult) -> Recommendation | None:
    """Spot the structural gap worth fixing, if any."""
    if not _has_withdrawal_portfolio(plan):
        return Recommendation(
            action="open_living_portfolio",
            reason="no_living_portfolio",
            parameters={"interest": DEFAULT_ADVISED_RETURN,
                        "portfolio_deposit": None,
                        "portfolio_subtype": "auto_broker"},
            missing_piece=_shortfall(baseline),
        )
    if _idle_surplus(plan):
        return Recommendation(
            action="invest_idle_surplus",
            reason="surplus_sits_in_cash",
            parameters={"portfolio_goal": "unlimited"},
            missing_piece=_shortfall(baseline),
        )
    return None


def apply(plan: Plan, recommendation: Recommendation) -> Plan:
    """The plan as it would be with the recommendation taken."""
    if recommendation.action == "open_living_portfolio":
        opened = Portfolio(
            balance=0.0,
            designation=PortfolioDesignation.WITHDRAW,
            kind=PortfolioType.BROKER_IL,
            goal=float("inf"),
            annual_return_pct=DEFAULT_ADVISED_RETURN,
            description="תיק מומלץ",
        )
        return replace(plan, portfolios=[*plan.portfolios, opened])
    if recommendation.action == "invest_idle_surplus":
        return replace(plan, portfolios=[
            replace(p, goal=float("inf")) if p.designation == PortfolioDesignation.WITHDRAW
            else p
            for p in plan.portfolios])
    return plan


def advise(plan: Plan, baseline: SolveResult, today: date | None = None) -> Recommendation | None:
    """Run the optimiser: propose, re-solve, and report whether it helped."""
    recommendation = propose(plan, baseline)
    if recommendation is None:
        return None

    improved = solve(apply(plan, recommendation), today)
    recommendation.improved = improved

    if improved.retire_index is None:
        recommendation.outcome = AdviceOutcome.NOT_BENEFICIAL
        return recommendation

    if baseline.retire_index is None:
        recommendation.outcome = AdviceOutcome.IMPROVED
        recommendation.months_saved = baseline.search_limit - improved.retire_index
        return recommendation

    saved = baseline.retire_index - improved.retire_index
    recommendation.months_saved = saved
    recommendation.outcome = (AdviceOutcome.IMPROVED if saved > 0
                              else AdviceOutcome.NOT_BENEFICIAL)
    return recommendation
