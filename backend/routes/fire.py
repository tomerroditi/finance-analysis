"""Early-retirement calculator API.

`POST /calculate` is a stateless projection: the caller posts a complete
scenario and gets back the verdict, the goal checklist, the monthly series the
charts need, and any optimiser recommendation.

`/plan` is the user's own plan: saved once, filled from their tracked data
(cash, investments, keren hishtalmut, pension, loans, spending and income), and
refreshed from it on every read. `GET /plan/projection` runs it — what the
dashboard card shows.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.fire.advice import advise
from backend.services.fire.models import Plan
from backend.services.fire.reference_form import plan_from_reference
from backend.services.fire.solver import solve
from backend.services.fire_plan_service import FirePlanService

router = APIRouter()


class FireScenario(ApiRequestModel):
    """A complete scenario, in the reference calculator's own field names.

    Keeping the reference's flat field names means a recorded scenario can be
    replayed verbatim, which is what the parity fixtures rely on.
    """

    fields: dict[str, str] = Field(
        ..., description="Flat form payload, e.g. {'dateOfBirth': '1990-01-01', ...}"
    )
    decumulation_return_pct: float | None = Field(
        None,
        description=(
            "Override for the return withdrawal portfolios earn after retirement. "
            "Leave it out: the engine reads the measured surface itself, on the "
            "bridge from retirement to this plan's own pension."
        ),
    )


class GoalRow(BaseModel):
    """One line of the goal-attainment checklist."""

    key: str
    label: str
    met: bool
    shortfall: float


class MonthRow(BaseModel):
    """One simulated month: age, balances and the flows in and out."""

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
    """The advice engine's proposed change and what it would buy."""

    action: str
    reason: str
    outcome: str
    months_saved: int
    missing_piece: float
    token: str


class AnnuityRow(BaseModel):
    """One line of the reference's annuity list."""

    owner: str
    source: str
    component: str
    recognised: bool
    claim_age: float
    monthly: float
    factor: float | None
    description: str


class WithdrawalRow(BaseModel):
    """One stretch of the drawdown plan: which bucket funded which years."""

    source: str
    description: str
    from_age: float
    to_age: float
    monthly_average: float


class SnapshotRow(BaseModel):
    """An asset card: what the plan holds now, and at retirement."""

    label: str
    year: int
    month: int
    net_worth: float
    breakdown: dict[str, float]
    shortfall_capital: float


class PensionIncomeRow(BaseModel):
    """What one person's pension will pay, and from what age."""

    owner: str
    age: float
    monthly: float


class FireProjection(BaseModel):
    """Everything the results view needs.

    `needs_setup` is the saved plan's answer when it cannot run yet — the
    calculator needs a date of birth, and tracked data carries none.
    """

    status: Literal["success", "goals_not_met", "no_result", "needs_setup"]
    retire_index: int | None
    retire_age: float | None
    retire_year: int | None
    retire_month: int | None
    search_limit_months: int
    inferred: bool
    goals: list[GoalRow]
    months: list[MonthRow]
    recommendation: RecommendationRow | None
    annuities: list[AnnuityRow]
    withdrawal_plan: list[WithdrawalRow]
    snapshots: list[SnapshotRow]
    pension_income: list[PensionIncomeRow]


class TrackedRow(BaseModel):
    """One tracked account the plan can hold as a row of its own.

    `fields` follow the account on every read (keyed by stem, without the row
    index); `seed` is only written when the row is first added.
    """

    source: str
    label: str
    fields: dict[str, str]
    seed: dict[str, str]


class TrackedData(BaseModel):
    """What the user's data says, in the calculator's own field names."""

    scalars: dict[str, str]
    rows: dict[str, list[TrackedRow]]


class FirePlan(BaseModel):
    """The user's plan, ready for the form."""

    saved: bool
    fields: dict[str, str]
    linked: list[str]
    tracked: TrackedData


class FirePlanUpsert(ApiRequestModel):
    """A plan to save."""

    fields: dict[str, str]
    linked: list[str] = Field(default_factory=list)


@router.get("/plan", response_model=FirePlan)
def get_plan(db: Session = Depends(get_database)) -> dict:
    """Return the saved plan, refreshed from tracked data, or one derived from it."""
    return FirePlanService(db).get_plan()


@router.put("/plan", response_model=FirePlan)
def save_plan(data: FirePlanUpsert, db: Session = Depends(get_database)) -> dict:
    """Save the plan."""
    return FirePlanService(db).save_plan(data.fields, data.linked)


@router.delete("/plan", response_model=FirePlan)
def reset_plan(db: Session = Depends(get_database)) -> dict:
    """Forget the saved plan and return the one derived from tracked data."""
    return FirePlanService(db).reset_plan()


@router.get("/plan/projection", response_model=FireProjection)
def plan_projection(db: Session = Depends(get_database)) -> FireProjection:
    """Run the user's plan, as saved and refreshed from tracked data."""
    fields = FirePlanService(db).runnable_fields()
    if fields is None:
        return _empty("needs_setup", 0, inferred=False)
    return _project(plan_from_reference(fields))


@router.post("/calculate", response_model=FireProjection)
def calculate(scenario: FireScenario) -> FireProjection:
    """Run a scenario and return its projection."""
    plan = plan_from_reference(scenario.fields)
    if scenario.decumulation_return_pct is not None:
        plan.decumulation_return_pct = scenario.decumulation_return_pct
    return _project(plan)


def _empty(status: str, search_limit: int, inferred: bool) -> FireProjection:
    """Build a projection with nothing to show."""
    return FireProjection(
        status=status,
        retire_index=None,
        retire_age=None,
        retire_year=None,
        retire_month=None,
        search_limit_months=search_limit,
        inferred=inferred,
        goals=[],
        months=[],
        recommendation=None,
        annuities=[],
        withdrawal_plan=[],
        snapshots=[],
        pension_income=[],
    )


def _project(plan: Plan) -> FireProjection:
    """Solve a plan from this month and shape the answer for the results view."""
    today = date.today().replace(day=1)
    result = solve(plan, today)

    if result.simulation is None:
        return _empty("no_result", result.search_limit, result.inferred)

    recommendation = advise(plan, result, today)
    retired = (
        result.simulation.months[result.retire_index - 1]
        if result.retire_index
        else None
    )

    return FireProjection(
        status="success" if result.succeeded else "goals_not_met",
        retire_index=result.retire_index,
        retire_age=result.retire_age,
        retire_year=retired.year if retired else None,
        retire_month=retired.month if retired else None,
        search_limit_months=result.search_limit,
        inferred=result.inferred,
        goals=[
            GoalRow(key=g.key, label=g.label, met=g.met, shortfall=g.shortfall)
            for g in result.goals
        ],
        months=[
            MonthRow(
                index=m.index,
                year=m.year,
                month=m.month,
                age=m.age,
                net_worth=m.net_worth,
                cash=m.cash,
                assets=m.assets,
                incomes=m.incomes,
                expenses=m.expenses,
                liabilities=m.liabilities,
            )
            for m in result.simulation.months
        ],
        annuities=[
            AnnuityRow(
                owner=a.owner,
                source=a.source,
                component=a.component,
                recognised=a.recognised,
                claim_age=a.claim_age,
                monthly=a.monthly,
                factor=a.factor,
                description=a.description,
            )
            for a in result.simulation.annuities
        ],
        withdrawal_plan=[
            WithdrawalRow(
                source=w.source,
                description=w.description,
                from_age=w.from_age,
                to_age=w.to_age,
                monthly_average=w.monthly_average,
            )
            for w in result.simulation.withdrawal_plan()
        ],
        snapshots=[
            SnapshotRow(
                label=s.label,
                year=s.year,
                month=s.month,
                net_worth=s.net_worth,
                breakdown=s.breakdown,
                shortfall_capital=s.shortfall_capital,
            )
            for s in result.simulation.snapshots()
        ],
        pension_income=[
            PensionIncomeRow(owner=owner, age=age, monthly=monthly)
            for owner, age, monthly in result.simulation.pension_income()
        ],
        recommendation=(
            RecommendationRow(
                action=recommendation.action,
                reason=recommendation.reason,
                outcome=recommendation.outcome.value,
                months_saved=recommendation.months_saved,
                missing_piece=recommendation.missing_piece,
                token=recommendation.token(),
            )
            if recommendation
            else None
        ),
    )
