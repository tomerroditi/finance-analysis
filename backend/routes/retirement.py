"""
Retirement planning API routes.

Provides endpoints for managing retirement goals and computing
FIRE projections with Israeli-specific savings vehicles.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.retirement_service import RetirementService

router = APIRouter()


class RetirementGoalUpsert(ApiRequestModel):
    """Request body for creating or updating the retirement goal."""

    current_age: int = Field(..., ge=18, le=100)
    gender: str = Field("male", pattern="^(male|female)$")
    target_retirement_age: int = Field(..., ge=30, le=100)
    life_expectancy: int = Field(90, ge=60, le=120)
    monthly_expenses_in_retirement: float = Field(..., gt=0)
    inflation_rate: float = Field(0.025, ge=0, le=0.2)
    expected_return_rate: float = Field(0.04, ge=-0.1, le=0.3)
    withdrawal_rate: float = Field(0.035, gt=0, le=0.1)
    pension_monthly_payout_estimate: float = Field(0.0, ge=0)
    keren_hishtalmut_balance: float = Field(0.0, ge=0)
    keren_hishtalmut_monthly_contribution: float = Field(0.0, ge=0)
    bituach_leumi_eligible: bool = True
    bituach_leumi_monthly_estimate: float = Field(2800.0, ge=0)
    other_passive_income: float = Field(0.0, ge=0)
    monthly_income: float | None = Field(None, ge=0)
    net_worth_override: float | None = Field(None, ge=0)
    monthly_expenses_override: float | None = Field(None, ge=0)
    total_investments_override: float | None = Field(None, ge=0)


class RetirementGoalResponse(BaseModel):
    """Response body for the retirement goal."""

    id: int
    current_age: int
    gender: str
    target_retirement_age: int
    life_expectancy: int
    monthly_expenses_in_retirement: float
    inflation_rate: float
    expected_return_rate: float
    withdrawal_rate: float
    pension_monthly_payout_estimate: float
    keren_hishtalmut_balance: float
    keren_hishtalmut_monthly_contribution: float
    bituach_leumi_eligible: bool
    bituach_leumi_monthly_estimate: float
    other_passive_income: float
    monthly_income: float | None = None
    net_worth_override: float | None = None
    monthly_expenses_override: float | None = None
    total_investments_override: float | None = None

    model_config = ConfigDict(from_attributes=True)


class RetirementStatusResponse(BaseModel):
    """Response body for current financial status."""

    net_worth: float
    avg_monthly_expenses: float
    avg_monthly_income: float
    savings_rate: float
    total_investments: float
    monthly_savings: float


class NetWorthProjectionPoint(BaseModel):
    """Single year in net worth projection."""

    age: int
    net_worth_optimistic: float
    net_worth_baseline: float
    net_worth_conservative: float


class IncomeProjectionPoint(BaseModel):
    """Single year in income projection."""

    age: int
    salary_savings: float
    portfolio_withdrawal: float
    pension: float
    bituach_leumi: float
    passive_income: float
    total_income: float
    expenses: float


class RetirementProjectionsResponse(BaseModel):
    """Response body for FIRE projections."""

    fire_number: float
    years_to_fire: int
    fire_age: int
    earliest_possible_retirement_age: int
    monthly_savings_needed: float
    progress_pct: float
    readiness: str
    portfolio_depleted_age: int | None = None
    target_retirement_age: int
    full_pension_age: int
    net_worth_projection: list[NetWorthProjectionPoint]
    income_projection: list[IncomeProjectionPoint]


class RetirementSuggestionsResponse(BaseModel):
    """Response body for auto-adjustment suggestions."""

    target_retirement_age: int
    monthly_expenses_in_retirement: float
    expected_return_rate: float
    life_expectancy: int


class SolveFieldResponse(BaseModel):
    """Response body for single field solve."""

    field: str
    value: float
    unit: str


class KerenHishtalmutBalanceResponse(BaseModel):
    """Response body for Keren Hishtalmut balance."""

    balance: float | None = None


class PensionForecastResponse(BaseModel):
    """Monthly pension estimated from the providers' own forecasts."""

    estimate: float | None = None
    with_deposits: float
    no_deposits: float
    as_of: str | None = None
    funds: int


class ScrapedDefaultsResponse(BaseModel):
    """Response body for auto-fillable values from scraped insurance data."""

    keren_hishtalmut_balance: float | None = None
    keren_hishtalmut_monthly_contribution: float | None = None
    pension_monthly_deposit: float | None = None
    avg_monthly_salary: float | None = None


@router.get("/goal", response_model=RetirementGoalResponse | None)
def get_goal(db: Session = Depends(get_database)) -> dict[str, Any] | None:
    """Get the retirement goal profile, or null if not configured."""
    service = RetirementService(db)
    return service.get_goal()


@router.put("/goal", response_model=RetirementGoalResponse)
def upsert_goal(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Create or update the retirement goal profile."""
    service = RetirementService(db)
    return service.upsert_goal(**data.model_dump())


@router.get("/status", response_model=RetirementStatusResponse)
def get_status(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Get current financial status from real tracked data."""
    service = RetirementService(db)
    return service.get_current_status()


@router.get("/projections", response_model=RetirementProjectionsResponse)
def get_projections(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Get FIRE projections from the saved goal."""
    service = RetirementService(db)
    return service.get_projections()


@router.post("/projections", response_model=RetirementProjectionsResponse)
def preview_projections(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Compute FIRE projections from provided goal params without saving."""
    service = RetirementService(db)
    return service.get_projections(goal_override=data.model_dump())


@router.get("/suggestions", response_model=RetirementSuggestionsResponse)
def get_suggestions(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Solve all adjustable fields from the saved goal."""
    service = RetirementService(db)
    return service.solve_all_fields()


@router.post("/suggestions", response_model=RetirementSuggestionsResponse)
def preview_suggestions(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Solve all adjustable fields from provided goal params without saving."""
    service = RetirementService(db)
    return service.solve_all_fields(goal_override=data.model_dump())


@router.get("/solve/{field}", response_model=SolveFieldResponse)
def solve_for_field(field: str, db: Session = Depends(get_database)) -> dict[str, Any]:
    """Solve for a field value that reaches FIRE at target retirement age."""
    service = RetirementService(db)
    return service.solve_for_field(field)


@router.get("/keren-hishtalmut-balance", response_model=KerenHishtalmutBalanceResponse)
def get_keren_hishtalmut_balance(
    db: Session = Depends(get_database),
) -> dict[str, float | None]:
    """Get the auto-detected Keren Hishtalmut balance.

    Covers both scraped insurance policies and manually-created KH
    investments — see ``InvestmentsService.get_hishtalmut_total_balance``.
    """
    service = RetirementService(db)
    balance = service.get_keren_hishtalmut_scraped_balance()
    return {"balance": balance}


@router.get("/pension-forecast", response_model=PensionForecastResponse)
def get_pension_forecast(
    current_age: int | None = Query(None, ge=0, le=120),
    target_retirement_age: int | None = Query(None, ge=0, le=120),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Estimate the monthly pension for a retirement plan's ages.

    Derived from each pension fund's published forecast (via the pension
    clearing house), with deposits stopping at ``target_retirement_age``.
    Ages default to the saved plan's.
    """
    return RetirementService(db).get_pension_forecast(
        current_age, target_retirement_age
    )


@router.get("/scraped-defaults", response_model=ScrapedDefaultsResponse)
def get_scraped_defaults(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Get all auto-fillable retirement goal values.

    Returns the Keren Hishtalmut balance (from scraped policies and
    manually-created KH investments alike), plus scraped monthly
    contribution and pension monthly deposit estimates. Values are null
    when no underlying data is available.
    """
    service = RetirementService(db)
    return service.get_scraped_defaults()
