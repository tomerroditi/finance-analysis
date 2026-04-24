"""
Retirement planning API routes.

Provides endpoints for managing retirement goals and computing
FIRE projections with Israeli-specific savings vehicles.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.retirement_service import RetirementService

router = APIRouter()


class RetirementGoalUpsert(BaseModel):
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
    portfolio_depleted_age: Optional[int] = None
    target_retirement_age: int
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

    balance: Optional[float] = None


class ScrapedDefaultsResponse(BaseModel):
    """Response body for auto-fillable values from scraped insurance data."""

    keren_hishtalmut_balance: Optional[float] = None
    keren_hishtalmut_monthly_contribution: Optional[float] = None
    pension_monthly_deposit: Optional[float] = None


@router.get("/goal", response_model=Optional[RetirementGoalResponse])
async def get_goal(db: Session = Depends(get_database)):
    """Get the retirement goal profile, or null if not configured."""
    service = RetirementService(db)
    return service.get_goal()


@router.put("/goal", response_model=RetirementGoalResponse)
async def upsert_goal(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
):
    """Create or update the retirement goal profile."""
    service = RetirementService(db)
    return service.upsert_goal(**data.model_dump())


@router.get("/status", response_model=RetirementStatusResponse)
async def get_status(db: Session = Depends(get_database)):
    """Get current financial status from real tracked data."""
    service = RetirementService(db)
    return service.get_current_status()


@router.get("/projections", response_model=RetirementProjectionsResponse)
async def get_projections(db: Session = Depends(get_database)):
    """Get FIRE projections from the saved goal."""
    service = RetirementService(db)
    return service.get_projections()


@router.post("/projections", response_model=RetirementProjectionsResponse)
async def preview_projections(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
):
    """Compute FIRE projections from provided goal params without saving."""
    service = RetirementService(db)
    return service.get_projections(goal_override=data.model_dump())


@router.get("/suggestions", response_model=RetirementSuggestionsResponse)
async def get_suggestions(db: Session = Depends(get_database)):
    """Solve all adjustable fields from the saved goal."""
    service = RetirementService(db)
    return service.solve_all_fields()


@router.post("/suggestions", response_model=RetirementSuggestionsResponse)
async def preview_suggestions(
    data: RetirementGoalUpsert, db: Session = Depends(get_database)
):
    """Solve all adjustable fields from provided goal params without saving."""
    service = RetirementService(db)
    return service.solve_all_fields(goal_override=data.model_dump())


@router.get("/solve/{field}", response_model=SolveFieldResponse)
async def solve_for_field(field: str, db: Session = Depends(get_database)):
    """Solve for a field value that reaches FIRE at target retirement age."""
    service = RetirementService(db)
    return service.solve_for_field(field)


@router.get("/keren-hishtalmut-balance", response_model=KerenHishtalmutBalanceResponse)
async def get_keren_hishtalmut_balance(db: Session = Depends(get_database)):
    """Get auto-detected Keren Hishtalmut balance from scraped insurance data."""
    service = RetirementService(db)
    balance = service.get_keren_hishtalmut_scraped_balance()
    return {"balance": balance}


@router.get("/scraped-defaults", response_model=ScrapedDefaultsResponse)
async def get_scraped_defaults(db: Session = Depends(get_database)):
    """Get all auto-fillable values from scraped insurance data.

    Returns Keren Hishtalmut balance and monthly contribution, plus
    pension monthly deposit estimate. Values are null when no scraped
    data is available.
    """
    service = RetirementService(db)
    return service.get_scraped_defaults()
