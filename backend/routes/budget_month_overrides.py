"""
Budget month override API routes.

Endpoints for reassigning a transaction to an adjacent month in the monthly
budget view without changing its real transaction date.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.budget_month_override_service import BudgetMonthOverrideService

router = APIRouter(tags=["budget-month-overrides"])


class SetMonthOverrideRequest(BaseModel):
    """Request to move a transaction/split to a different budget month."""

    source_type: Literal["transaction", "split"]
    source_id: int
    source_table: str
    override_year: int
    override_month: int


@router.post("/")
async def set_month_override(
    request: SetMonthOverrideRequest,
    db: Session = Depends(get_database),
):
    """Reassign a transaction to an adjacent month for the monthly budget."""
    service = BudgetMonthOverrideService(db)
    return service.set_override(
        source_type=request.source_type,
        source_id=request.source_id,
        source_table=request.source_table,
        override_year=request.override_year,
        override_month=request.override_month,
    )


@router.get("/")
async def get_month_overrides(db: Session = Depends(get_database)):
    """Get all budget month overrides."""
    service = BudgetMonthOverrideService(db)
    return service.get_all()


@router.delete("/{override_id}")
async def delete_month_override(
    override_id: int,
    db: Session = Depends(get_database),
):
    """Remove a budget month override (transaction reverts to its real month)."""
    service = BudgetMonthOverrideService(db)
    service.remove_override(override_id)
    return {"status": "success"}
