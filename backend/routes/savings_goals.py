"""Savings goals API routes.

CRUD for goals plus the surfaces the allocation engine needs: the waterfall
order, the per-month allocation view the budget page renders, transaction
links, and the previewable history rebuild.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.savings_goal_service import SavingsGoalService

router = APIRouter()


class SavingsGoalCreate(ApiRequestModel):
    """Request body for creating a savings goal."""

    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    opening_balance: float = Field(0.0, ge=0)
    priority: Optional[int] = Field(None, ge=0)
    monthly_cap: Optional[float] = Field(None, gt=0)
    start_month: Optional[str] = None
    target_date: Optional[str] = None
    contribution_category: Optional[str] = None
    contribution_tags: Optional[str] = None
    notes: Optional[str] = None


class SavingsGoalUpdate(ApiRequestModel):
    """Request body for updating a savings goal (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    target_amount: Optional[float] = Field(None, gt=0)
    opening_balance: Optional[float] = Field(None, ge=0)
    monthly_cap: Optional[float] = Field(None, gt=0)
    start_month: Optional[str] = None
    target_date: Optional[str] = None
    contribution_category: Optional[str] = None
    contribution_tags: Optional[str] = None
    notes: Optional[str] = None


class SavingsGoalReorder(ApiRequestModel):
    """Request body for setting the waterfall order (first id is funded first)."""

    goal_ids: list[int] = Field(..., min_length=1)


class SavingsGoalLinkCreate(ApiRequestModel):
    """Request body for attaching a transaction to a goal."""

    source_type: Literal["transaction", "split"] = "transaction"
    source_id: int
    source_table: str = Field(..., min_length=1)
    link_type: Literal["contribution", "utilization"]


class SavingsGoalRebuild(BaseModel):
    """Request body for restating allocation history."""

    from_month: Optional[str] = None
    dry_run: bool = True


@router.get("/")
def list_goals(db: Session = Depends(get_database)):
    """Return all savings goals enriched with progress metrics."""
    return SavingsGoalService(db).get_all()


@router.post("/")
def create_goal(data: SavingsGoalCreate, db: Session = Depends(get_database)):
    """Create a new savings goal and return the refreshed goal list."""
    return SavingsGoalService(db).create(**data.model_dump(exclude_none=True))


@router.put("/{goal_id}")
def update_goal(
    goal_id: int, data: SavingsGoalUpdate, db: Session = Depends(get_database)
):
    """Update an existing savings goal."""
    return SavingsGoalService(db).update(goal_id, **data.model_dump(exclude_unset=True))


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_database)):
    """Delete a savings goal along with its allocations and links."""
    SavingsGoalService(db).delete(goal_id)
    return {"status": "deleted"}


@router.post("/reorder")
def reorder_goals(data: SavingsGoalReorder, db: Session = Depends(get_database)):
    """Set the waterfall order. Applies to future allocations only."""
    return SavingsGoalService(db).reorder(data.goal_ids)


@router.post("/{goal_id}/close")
def close_goal(goal_id: int, db: Session = Depends(get_database)):
    """Close a goal, freezing its allocation history."""
    return SavingsGoalService(db).close(goal_id)


@router.post("/{goal_id}/reopen")
def reopen_goal(goal_id: int, db: Session = Depends(get_database)):
    """Reopen a closed goal so it absorbs surplus again."""
    return SavingsGoalService(db).reopen(goal_id)


@router.get("/free-cash")
def get_free_cash(db: Session = Depends(get_database)):
    """Return the pool of tracked money no goal has earmarked."""
    return SavingsGoalService(db).get_free_cash()


@router.get("/allocations/{year}/{month}")
def get_month_allocations(year: int, month: int, db: Session = Depends(get_database)):
    """Return how much each goal received in one month, for the budget view."""
    return SavingsGoalService(db).get_month_allocations(year, month)


@router.post("/rebuild")
def rebuild_allocations(data: SavingsGoalRebuild, db: Session = Depends(get_database)):
    """Restate allocation history under the current priorities.

    Defaults to a dry run so the caller can show the before/after diff before
    committing. Closed goals are never restated.
    """
    return SavingsGoalService(db).rebuild(
        from_month=data.from_month, dry_run=data.dry_run
    )


@router.get("/links")
def list_links(goal_id: Optional[int] = None, db: Session = Depends(get_database)):
    """Return transaction links, optionally scoped to one goal."""
    return SavingsGoalService(db).get_links(goal_id)


@router.post("/{goal_id}/links")
def link_transaction(
    goal_id: int, data: SavingsGoalLinkCreate, db: Session = Depends(get_database)
):
    """Attach a transaction to a goal as a contribution or a utilization."""
    return SavingsGoalService(db).link_transaction(goal_id=goal_id, **data.model_dump())


@router.delete("/links/{link_id}")
def unlink_transaction(link_id: int, db: Session = Depends(get_database)):
    """Detach a transaction from its goal."""
    return SavingsGoalService(db).unlink_transaction(link_id)
