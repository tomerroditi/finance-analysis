"""
Retirement planning API routes.

Provides endpoints for managing retirement goals and computing
FIRE projections with Israeli-specific savings vehicles.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
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

    class Config:
        from_attributes = True


@router.get("/goal")
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


@router.get("/status")
async def get_status(db: Session = Depends(get_database)):
    """Get current financial status from real tracked data."""
    service = RetirementService(db)
    return service.get_current_status()


@router.get("/projections")
async def get_projections(db: Session = Depends(get_database)):
    """Get FIRE projections and retirement income analysis."""
    service = RetirementService(db)
    return service.get_projections()


@router.get("/solve/{field}")
async def solve_for_field(field: str, db: Session = Depends(get_database)):
    """Solve for a field value that reaches FIRE at target retirement age."""
    service = RetirementService(db)
    return service.solve_for_field(field)


@router.get("/keren-hishtalmut-balance")
async def get_keren_hishtalmut_balance(db: Session = Depends(get_database)):
    """Get auto-detected Keren Hishtalmut balance from scraped insurance data."""
    service = RetirementService(db)
    balance = service.get_keren_hishtalmut_scraped_balance()
    return {"balance": balance}
