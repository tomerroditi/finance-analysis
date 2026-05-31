"""Savings goals API routes.

CRUD endpoints for user-defined savings goals with derived progress metrics.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.savings_goal_service import SavingsGoalService

router = APIRouter()


class SavingsGoalCreate(BaseModel):
    """Request body for creating a savings goal."""

    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(0.0, ge=0)
    target_date: Optional[str] = None
    notes: Optional[str] = None


class SavingsGoalUpdate(BaseModel):
    """Request body for updating a savings goal (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    target_amount: Optional[float] = Field(None, gt=0)
    current_amount: Optional[float] = Field(None, ge=0)
    target_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def list_goals(db: Session = Depends(get_database)):
    """Return all savings goals enriched with progress metrics."""
    return SavingsGoalService(db).get_all()


@router.post("/")
async def create_goal(data: SavingsGoalCreate, db: Session = Depends(get_database)):
    """Create a new savings goal."""
    return SavingsGoalService(db).create(**data.model_dump())


@router.put("/{goal_id}")
async def update_goal(
    goal_id: int, data: SavingsGoalUpdate, db: Session = Depends(get_database)
):
    """Update an existing savings goal."""
    return SavingsGoalService(db).update(goal_id, **data.model_dump(exclude_unset=True))


@router.delete("/{goal_id}")
async def delete_goal(goal_id: int, db: Session = Depends(get_database)):
    """Delete a savings goal."""
    SavingsGoalService(db).delete(goal_id)
    return {"status": "deleted"}
