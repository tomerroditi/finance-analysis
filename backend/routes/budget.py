"""
Budget API routes.

Provides endpoints for budget rule management.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.budget_repository import BudgetRepository

router = APIRouter()


class BudgetRuleCreate(BaseModel):
    name: str
    amount: float
    category: str
    tags: str
    month: Optional[int] = None
    year: Optional[int] = None


class BudgetRuleUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    tags: Optional[str] = None


@router.get("/rules")
async def get_budget_rules(
    db: Session = Depends(get_database)
):
    """Get all budget rules."""
    repo = BudgetRepository(db)
    df = repo.read_all()
    return df.to_dict(orient="records")


@router.get("/rules/{year}/{month}")
async def get_budget_rules_by_month(
    year: int,
    month: int,
    db: Session = Depends(get_database)
):
    """Get budget rules for a specific month."""
    repo = BudgetRepository(db)
    df = repo.read_by_month(year, month)
    return df.to_dict(orient="records")


@router.post("/rules")
async def create_budget_rule(
    rule: BudgetRuleCreate,
    db: Session = Depends(get_database)
):
    """Create a new budget rule."""
    repo = BudgetRepository(db)
    try:
        repo.add(rule.name, rule.amount, rule.category, rule.tags, rule.month, rule.year)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rules/{rule_id}")
async def update_budget_rule(
    rule_id: int,
    rule: BudgetRuleUpdate,
    db: Session = Depends(get_database)
):
    """Update a budget rule."""
    repo = BudgetRepository(db)
    try:
        updates = {k: v for k, v in rule.dict().items() if v is not None}
        repo.update(rule_id, **updates)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/rules/{rule_id}")
async def delete_budget_rule(
    rule_id: int,
    db: Session = Depends(get_database)
):
    """Delete a budget rule."""
    repo = BudgetRepository(db)
    repo.delete(rule_id)
    return {"status": "success"}
