"""Early-retirement calculator API.

A stateless projection endpoint: the caller posts a complete scenario and gets
back the verdict, the goal checklist, the monthly series the charts need, and
any optimiser recommendation. Nothing is persisted — wiring this to the user's
tracked data is a separate, later decision.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.routes.schemas import ApiRequestModel
from backend.services.fire.advice import advise
from backend.services.fire.reference_form import plan_from_reference
from backend.services.fire.solver import solve

router = APIRouter()


class FireScenario(ApiRequestModel):
    """A complete scenario, in the reference calculator's own field names.

    Keeping the reference's flat field names means a recorded scenario can be
    replayed verbatim, which is what the parity fixtures rely on.
    """

    fields: dict[str, str] = Field(
        ..., description="Flat form payload, e.g. {'dateOfBirth': '1990-01-01', ...}"
    )
    decumulation_return_pct: Optional[float] = Field(
        None,
        description=(
            "Override for the return withdrawal portfolios earn after retirement. "
            "Leave it out: the engine reads the measured surface itself, on the "
            "bridge from retirement to this plan's own pension."
        ),
    )


class GoalRow(BaseModel):
    key: str
    label: str
    met: bool
    shortfall: float


class MonthRow(BaseModel):
    index: int
    year: int
    month: int
    age: float
    net_worth: float
    cash: float
    assets: dict[str, float]
    incomes: dict[str, float]
    expenses: dict[str, float]
    liabilities: float


class RecommendationRow(BaseModel):
    action: str
    reason: str
    outcome: str
    months_saved: int
    missing_piece: float
    token: str


class FireProjection(BaseModel):
    """Everything the results view needs."""

    status: Literal["success", "goals_not_met", "no_result"]
    retire_index: Optional[int]
    retire_age: Optional[float]
    retire_year: Optional[int]
    retire_month: Optional[int]
    search_limit_months: int
    inferred: bool
    goals: list[GoalRow]
    months: list[MonthRow]
    recommendation: Optional[RecommendationRow]


@router.post("/calculate", response_model=FireProjection)
def calculate(scenario: FireScenario) -> FireProjection:
    """Run a scenario and return its projection."""
    plan = plan_from_reference(scenario.fields)
    if scenario.decumulation_return_pct is not None:
        plan.decumulation_return_pct = scenario.decumulation_return_pct

    today = date.today().replace(day=1)
    result = solve(plan, today)

    if result.simulation is None:
        return FireProjection(
            status="no_result", retire_index=None, retire_age=None,
            retire_year=None, retire_month=None,
            search_limit_months=result.search_limit, inferred=result.inferred,
            goals=[], months=[], recommendation=None,
        )

    recommendation = advise(plan, result, today)
    retired = result.simulation.months[result.retire_index - 1] if result.retire_index else None

    return FireProjection(
        status="success" if result.succeeded else "goals_not_met",
        retire_index=result.retire_index,
        retire_age=result.retire_age,
        retire_year=retired.year if retired else None,
        retire_month=retired.month if retired else None,
        search_limit_months=result.search_limit,
        inferred=result.inferred,
        goals=[GoalRow(key=g.key, label=g.label, met=g.met, shortfall=g.shortfall)
               for g in result.goals],
        months=[
            MonthRow(index=m.index, year=m.year, month=m.month, age=m.age,
                     net_worth=m.net_worth, cash=m.cash, assets=m.assets,
                     incomes=m.incomes, expenses=m.expenses, liabilities=m.liabilities)
            for m in result.simulation.months
        ],
        recommendation=(
            RecommendationRow(
                action=recommendation.action, reason=recommendation.reason,
                outcome=recommendation.outcome.value,
                months_saved=recommendation.months_saved,
                missing_piece=recommendation.missing_piece,
                token=recommendation.token(),
            ) if recommendation else None
        ),
    )
