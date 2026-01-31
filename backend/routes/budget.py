"""
Budget API routes.

Provides endpoints for budget rule management, analysis, and project management.
"""

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.naming_conventions import ALL_TAGS
from backend.services.budget_service import (
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
)

router = APIRouter()


class BudgetRuleCreate(BaseModel):
    name: str
    amount: float
    category: str
    tags: str | List[str]
    month: Optional[int] = None
    year: Optional[int] = None


class BudgetRuleUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    tags: Optional[str | List[str]] = None


class ProjectCreate(BaseModel):
    category: str
    total_budget: float


class ProjectUpdate(BaseModel):
    total_budget: float


@router.get("/rules")
async def get_budget_rules(db: Session = Depends(get_database)):
    """Get all budget rules."""
    service = BudgetService(db)
    df = service.get_all_rules()
    return df.to_dict(orient="records")


@router.get("/rules/{year}/{month}")
async def get_budget_rules_by_month(
    year: int, month: int, db: Session = Depends(get_database)
):
    """Get budget rules for a specific month."""
    service = MonthlyBudgetService(db)
    df = service.get_month_rules(year, month)
    return df.to_dict(orient="records")


@router.post("/rules")
async def create_budget_rule(
    rule: BudgetRuleCreate, db: Session = Depends(get_database)
):
    """Create a new budget rule."""
    service = MonthlyBudgetService(db)
    budget_rules = service.get_all_rules()
    is_valid, msg = service.validate_rule_inputs(
        budget_rules,
        rule.name,
        rule.category,
        rule.tags.split(";") if isinstance(rule.tags, str) else rule.tags,
        rule.amount,
        rule.year,
        rule.month,
        None,
    )
    if not is_valid:
        raise ValueError(msg)

    service.add_rule(
        rule.name, rule.amount, rule.category, rule.tags, rule.month, rule.year
    )
    return {"status": "success"}


@router.put("/rules/{rule_id}")
async def update_budget_rule(
    rule_id: int, rule: BudgetRuleUpdate, db: Session = Depends(get_database)
):
    """Update a budget rule."""
    service = BudgetService(db)
    updates = {k: v for k, v in rule.dict().items() if v is not None}
    service.update_rule(rule_id, **updates)
    return {"status": "success"}


@router.delete("/rules/{rule_id}")
async def delete_budget_rule(rule_id: int, db: Session = Depends(get_database)):
    """Delete a budget rule."""
    service = BudgetService(db)
    service.delete_rule(rule_id)
    return {"status": "success"}


@router.post("/rules/{year}/{month}/copy")
async def copy_previous_month_rules(
    year: int, month: int, db: Session = Depends(get_database)
):
    """Copy budget rules from the previous month."""
    service = MonthlyBudgetService(db)
    budget_rules = service.get_all_rules()
    result = service.copy_last_month_rules(year, month, budget_rules)
    if result is None:
        raise HTTPException(
            status_code=404, detail="No rules found in the previous month to copy."
        )
    return {"status": "success", "message": result}


# --- Analysis Endpoints ---


@router.get("/analysis/{year}/{month}")
async def get_monthly_analysis(
    year: int, month: int, db: Session = Depends(get_database)
):
    """Get full monthly budget analysis."""
    from backend.services.pending_refunds_service import PendingRefundsService

    service = MonthlyBudgetService(db)
    view = service.get_monthly_budget_view(year, month)
    project_summary = service.get_monthly_project_spending_summary(year, month)

    # Get pending refunds summary
    pending_service = PendingRefundsService(db)
    pending_refunds = pending_service.get_all_pending(status="pending")
    budget_adjustment = pending_service.get_budget_adjustment(year, month)

    return {
        "rules": view if view else [],
        "project_spending": project_summary,
        "pending_refunds": {
            "items": pending_refunds,
            "total_expected": budget_adjustment,
        },
    }


# --- Project Endpoints ---


@router.get("/projects")
async def get_projects(db: Session = Depends(get_database)):
    """Get all project names."""
    service = ProjectBudgetService(db)
    return service.get_all_projects_names()


@router.get("/projects/available")
async def get_available_categories_for_new_project(db: Session = Depends(get_database)):
    """Get available categories for a new project."""
    service = ProjectBudgetService(db)
    return service.get_available_categories_for_new_project()


@router.post("/projects")
async def create_project(project: ProjectCreate, db: Session = Depends(get_database)):
    """Create a new project."""
    service = ProjectBudgetService(db)
    service.create_project(project.category, project.total_budget)
    return {"status": "success"}


@router.put("/projects/{name}")
async def update_project(
    name: str, project: ProjectUpdate, db: Session = Depends(get_database)
):
    """Update project total budget."""
    service = ProjectBudgetService(db)
    service.update_project(name, project.total_budget)
    return {"status": "success"}


@router.delete("/projects/{name}")
async def delete_project(name: str, db: Session = Depends(get_database)):
    """Delete a project."""
    service = ProjectBudgetService(db)
    service.delete_project(name)
    return {"status": "success"}


@router.get("/projects/{name}")
async def get_project_details(name: str, db: Session = Depends(get_database)):
    """Get project details including rules and transactions."""
    service = ProjectBudgetService(db)
    rules = service.get_rules_for_project(name)
    transactions = service.get_project_transactions(name)

    view = []

    # Total Project Rule
    total_rule = pd.DataFrame()
    if not rules.empty:
        # Find where tags == [ALL_TAGS].
        total_rule = rules[rules["tags"].apply(lambda x: x == [ALL_TAGS])]

    # Ensure transactions is JSON serializable (handle NaNs)
    transactions_processed = transactions.where(pd.notnull(transactions), None)
    total_spent = transactions_processed["amount"].sum() * -1

    if not total_rule.empty:
        view.append(
            {
                "rule": total_rule.iloc[0].to_dict(),
                "current_amount": total_spent,
                "data": transactions_processed.to_dict(orient="records"),
                "allow_edit": True,
                "allow_delete": False,
            }
        )
        rules = rules.drop(total_rule.index)

    # Per tag rules
    for _, rule in rules.iterrows():
        tags = rule["tags"]
        # Filter transactions for these tags
        tag_txns = transactions_processed[transactions_processed["tag"].isin(tags)]
        spent = tag_txns["amount"].sum() * -1

        view.append(
            {
                "rule": rule.to_dict(),
                "current_amount": spent,
                "data": tag_txns.to_dict(orient="records"),
                "allow_edit": True,
                "allow_delete": True,
            }
        )

    return {"name": name, "rules": view, "total_spent": total_spent}
