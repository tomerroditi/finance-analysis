"""Savings goals API routes.

CRUD for goals, money put into and taken out of them, funding the month's
suggestions, covering a free-cash shortfall, the month view the budget page
renders, the timeline, transaction links and the yearly savings target.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.savings_goals import SavingsGoalService

router = APIRouter()


class SavingsGoalCreate(ApiRequestModel):
    """Request body for creating a savings goal."""

    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    initial_amount: float = Field(0.0, ge=0)
    priority: int | None = Field(None, ge=0)
    monthly_amount: float | None = Field(None, gt=0)
    start_month: str | None = None
    target_date: str | None = None
    contribution_category: str | None = None
    contribution_tags: str | None = None
    utilization_category: str | None = None
    utilization_tags: str | None = None
    notes: str | None = None


class SavingsGoalUpdate(ApiRequestModel):
    """Request body for updating a savings goal (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=120)
    target_amount: float | None = Field(None, gt=0)
    monthly_amount: float | None = Field(None, gt=0)
    start_month: str | None = None
    target_date: str | None = None
    contribution_category: str | None = None
    contribution_tags: str | None = None
    utilization_category: str | None = None
    utilization_tags: str | None = None
    notes: str | None = None


class YearlySavingsTargetUpdate(ApiRequestModel):
    """Request body for a year's savings target; ``None`` clears it."""

    target_amount: float | None = Field(None, gt=0)


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


class SavingsGoalEntryCreate(ApiRequestModel):
    """Request body for putting money into a goal (positive) or taking it out."""

    amount: float
    date: str | None = None
    note: str | None = Field(None, max_length=500)


class SavingsGoalFund(ApiRequestModel):
    """Request body for funding this month's suggestions."""

    goal_ids: list[int] | None = None


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
    """Delete a savings goal along with its entries and links."""
    SavingsGoalService(db).delete(goal_id)
    return {"status": "deleted"}


@router.post("/reorder")
def reorder_goals(
    data: SavingsGoalReorder, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Set the list order of the goals."""
    return SavingsGoalService(db).reorder(data.goal_ids)


@router.post("/{goal_id}/close")
def close_goal(
    goal_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Close a goal, handing what it still holds back to free cash."""
    return SavingsGoalService(db).close(goal_id)


@router.post("/{goal_id}/reopen")
def reopen_goal(
    goal_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Reopen a closed goal, restoring what closing it handed back."""
    return SavingsGoalService(db).reopen(goal_id)


@router.post("/{goal_id}/entries")
def add_entry(
    goal_id: int, data: SavingsGoalEntryCreate, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Put money into a goal (positive amount) or take it out (negative)."""
    return SavingsGoalService(db).add_entry(goal_id, data.amount, data.date, data.note)


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Undo one entry."""
    return SavingsGoalService(db).delete_entry(entry_id)


@router.post("/fund")
def fund_goals(
    data: SavingsGoalFund, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Put this month's suggested amounts into goals, as far as free cash goes."""
    return SavingsGoalService(db).fund(data.goal_ids)


@router.get("/yearly")
def get_yearly_savings(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Return how much each year saved, its target, and this year's pace."""
    return SavingsGoalService(db).get_yearly_savings()


@router.put("/yearly/{year}/target")
def set_yearly_target(
    year: int,
    data: YearlySavingsTargetUpdate,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Set or clear how much to save in ``year``; returns the yearly view."""
    return SavingsGoalService(db).set_yearly_target(year, data.target_amount)


@router.get("/free-cash")
def get_free_cash(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Return the bank and cash money no goal holds, with a plan to cover a shortfall."""
    return SavingsGoalService(db).get_free_cash()


@router.post("/free-cash/cover")
def cover_free_cash(db: Session = Depends(get_database)) -> list[dict[str, Any]]:
    """Take a free-cash shortfall back from the goals, lowest in the list first."""
    return SavingsGoalService(db).cover()


@router.get("/timeline")
def get_timeline(
    months: int = Query(12, ge=0, le=600), db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return each goal's balance month by month, with free cash beside it.

    ``months`` trims to the trailing window the dashboard chart shows;
    ``0`` returns the whole history (the "all time" range).
    """
    return SavingsGoalService(db).get_timeline(months=months or None)


@router.get("/month/{year}/{month}")
def get_month(
    year: int, month: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return what moved into and out of each goal in one month, for the budget view."""
    return SavingsGoalService(db).get_month(year, month)


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
    """Attach a transaction to a goal as income or as spending."""
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
