"""Savings goals API routes.

CRUD for goals plus the surfaces the allocation engine needs: the waterfall
order, the per-month allocation view the budget page renders, transaction
links, and the previewable history rebuild.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.savings_goals import SavingsGoalService

router = APIRouter()


class SavingsGoalCreate(ApiRequestModel):
    """Request body for creating a savings goal."""

    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    opening_balance: float = Field(0.0, ge=0)
    priority: int | None = Field(None, ge=0)
    monthly_cap: float | None = Field(None, gt=0)
    start_month: str | None = None
    target_date: str | None = None
    contribution_category: str | None = None
    contribution_tags: str | None = None
    utilization_category: str | None = None
    utilization_tags: str | None = None
    kind: Literal["cash", "investment"] = "cash"
    notes: str | None = None


class SavingsGoalUpdate(ApiRequestModel):
    """Request body for updating a savings goal (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=120)
    target_amount: float | None = Field(None, gt=0)
    opening_balance: float | None = Field(None, ge=0)
    monthly_cap: float | None = Field(None, gt=0)
    start_month: str | None = None
    target_date: str | None = None
    contribution_category: str | None = None
    contribution_tags: str | None = None
    utilization_category: str | None = None
    utilization_tags: str | None = None
    notes: str | None = None


class SavingsGoalReorder(ApiRequestModel):
    """Request body for setting the waterfall order (first id is funded first)."""

    goal_ids: list[int] = Field(..., min_length=1)


class SavingsGoalLinkCreate(ApiRequestModel):
    """Request body for attaching a transaction to a goal."""

    source_type: Literal["transaction", "split"] = "transaction"
    source_id: int
    source_table: str = Field(..., min_length=1)
    link_type: Literal["contribution", "utilization"]


class SavingsGoalSpendingLink(ApiRequestModel):
    """Request body for naming the spending a goal pays for."""

    #: ``None`` clears the goal's rule.
    category: str | None = Field(None, min_length=1)
    #: Narrows ``category``; empty or ``["all_tags"]`` covers every tag.
    tags: list[str] | None = None


class SavingsGoalInvestmentCreate(ApiRequestModel):
    """Request body for earmarking an investment against a goal."""

    investment_id: int
    #: ``None`` earmarks whatever is left of the holding, so the goal keeps
    #: tracking its value without the user retyping a number.
    amount: float | None = Field(None, gt=0)


class SavingsGoalRebuild(BaseModel):
    """Request body for restating allocation history."""

    from_month: str | None = None
    dry_run: bool = True


@router.get("/")
def list_goals(db: Session = Depends(get_database)) -> list[dict[str, Any]]:
    """Return all savings goals enriched with progress metrics."""
    return SavingsGoalService(db).get_all()


@router.post("/")
def create_goal(
    data: SavingsGoalCreate, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Create a new savings goal and return the refreshed goal list."""
    return SavingsGoalService(db).create(**data.model_dump(exclude_none=True))


@router.put("/{goal_id}")
def update_goal(
    goal_id: int, data: SavingsGoalUpdate, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Update an existing savings goal and return the refreshed goal list."""
    return SavingsGoalService(db).update(goal_id, **data.model_dump(exclude_unset=True))


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_database)) -> dict[str, str]:
    """Delete a savings goal along with its allocations and links."""
    SavingsGoalService(db).delete(goal_id)
    return {"status": "deleted"}


@router.post("/reorder")
def reorder_goals(
    data: SavingsGoalReorder, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Set the waterfall order and restate allocation history under it."""
    return SavingsGoalService(db).reorder(data.goal_ids)


@router.post("/{goal_id}/close")
def close_goal(
    goal_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Close a goal, freezing its allocation history."""
    return SavingsGoalService(db).close(goal_id)


@router.post("/{goal_id}/reopen")
def reopen_goal(
    goal_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Reopen a closed goal so it absorbs surplus again."""
    return SavingsGoalService(db).reopen(goal_id)


@router.get("/free-cash")
def get_free_cash(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Return the pool of tracked money no goal has earmarked."""
    return SavingsGoalService(db).get_free_cash()


@router.get("/free-cash/before")
def get_free_cash_before(
    month: str,
    goal_id: int | None = None,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return the free cash that existed when a goal starting in ``month`` began.

    ``goal_id`` leaves the goal being edited out of the figure, so it can be
    used as that goal's opening balance.
    """
    return SavingsGoalService(db).get_free_cash_before(month, goal_id)


@router.get("/timeline")
def get_timeline(
    months: int = Query(12, ge=0, le=600), db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return the per-month allocation history plus the free-cash pool.

    ``months`` trims to the trailing window the dashboard chart shows;
    ``0`` returns the whole history (the "all time" range).
    """
    return SavingsGoalService(db).get_timeline(months=months or None)


@router.get("/allocations/{year}/{month}")
def get_month_allocations(
    year: int, month: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return how much each goal received in one month, for the budget view."""
    return SavingsGoalService(db).get_month_allocations(year, month)


@router.post("/rebuild")
def rebuild_allocations(
    data: SavingsGoalRebuild, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Restate allocation history under the current priorities.

    Defaults to a dry run so the caller can show the before/after diff before
    committing. Closed goals are never restated.
    """
    return SavingsGoalService(db).rebuild(
        from_month=data.from_month, dry_run=data.dry_run
    )


@router.get("/links")
def list_links(
    goal_id: int | None = None, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return transaction links, optionally scoped to one goal."""
    return SavingsGoalService(db).get_links(goal_id)


@router.post("/{goal_id}/links")
def link_transaction(
    goal_id: int, data: SavingsGoalLinkCreate, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Attach a transaction to a goal as a contribution or a utilization."""
    return SavingsGoalService(db).link_transaction(goal_id=goal_id, **data.model_dump())


@router.delete("/links/{link_id}")
def unlink_transaction(
    link_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Detach a transaction from its goal."""
    return SavingsGoalService(db).unlink_transaction(link_id)


@router.put("/{goal_id}/spending-link")
def set_spending_link(
    goal_id: int, data: SavingsGoalSpendingLink, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Spend a category (optionally narrowed to tags) out of a goal; ``null`` clears it."""
    return SavingsGoalService(db).set_spending_link(goal_id, data.category, data.tags)


@router.get("/investments/available")
def list_available_investments(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Return open investments with how much of each is still unearmarked."""
    return SavingsGoalService(db).get_available_investments()


@router.get("/investments")
def list_investment_backings(
    goal_id: int | None = None, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return investment earmarks, optionally scoped to one goal."""
    return SavingsGoalService(db).get_investment_backings(goal_id)


@router.post("/{goal_id}/investments")
def link_investment(
    goal_id: int,
    data: SavingsGoalInvestmentCreate,
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Earmark an investment holding against a goal."""
    return SavingsGoalService(db).link_investment(goal_id=goal_id, **data.model_dump())


@router.delete("/investments/{backing_id}")
def unlink_investment(
    backing_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Release an investment earmark."""
    return SavingsGoalService(db).unlink_investment(backing_id)
