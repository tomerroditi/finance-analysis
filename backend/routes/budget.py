"""
Budget API routes.

Provides endpoints for budget rule management, analysis, and project management.
"""

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.budget_service import (
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
    YearlyBudgetService,
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


class YearlyRuleCreate(BaseModel):
    name: str
    amount: float
    category: str
    tags: str | List[str]
    year: int


class YearlyRuleUpdate(BaseModel):
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
def get_budget_rules(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all budget rules."""
    service = BudgetService(db)
    df = service.get_all_rules()
    return df.to_dict(orient="records")


@router.get("/rules/{year}/{month}")
def get_budget_rules_by_month(
    year: int, month: int, db: Session = Depends(get_database)
) -> list[dict]:
    """Get budget rules for a specific month."""
    service = MonthlyBudgetService(db)
    df = service.get_month_rules(year, month)
    return df.to_dict(orient="records")


@router.post("/rules")
def create_budget_rule(
    rule: BudgetRuleCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new budget rule."""
    service = MonthlyBudgetService(db)
    try:
        service.create_rule(
            rule.name, rule.amount, rule.category, rule.tags, rule.month, rule.year
        )
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/rules/{rule_id}")
def update_budget_rule(
    rule_id: int, rule: BudgetRuleUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update a budget rule.

    This route is shared between monthly and project rules (both are edited
    through the same ``rule_id``), so it uses ``MonthlyBudgetService`` — its
    ``update_rule`` override guards monthly edits against claiming a
    yearly-owned tag and is a no-op passthrough for project rules.
    """
    service = MonthlyBudgetService(db)
    updates = {k: v for k, v in rule.model_dump().items() if v is not None}
    try:
        service.update_rule(rule_id, **updates)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/rules/{rule_id}")
def delete_budget_rule(
    rule_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a budget rule."""
    service = BudgetService(db)
    service.delete_rule(rule_id)
    return {"status": "success"}


@router.post("/rules/{year}/{month}/copy")
def copy_previous_month_rules(
    year: int, month: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Copy budget rules from the previous calendar month into the given month.

    Parameters
    ----------
    year : int
        Target year to copy rules into.
    month : int
        Target month (1–12) to copy rules into.

    Returns
    -------
    dict
        ``{"status": "success", "message": str}`` on success.

    Raises
    ------
    HTTPException
        404 if the previous month has no rules to copy.
    """
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
def get_monthly_analysis(
    year: int,
    month: int,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return full budget vs. actual analysis for a calendar month.

    Parameters
    ----------
    year : int
        The year of the month to analyse.
    month : int
        The month (1–12) to analyse.
    include_split_parents : bool, optional
        When ``True``, include the original parent transactions of splits
        alongside the individual split rows. Defaults to ``False``.

    Returns
    -------
    dict
        Monthly analysis including budget rules, actual spending per
        category/tag, and remaining amounts.
    """
    service = MonthlyBudgetService(db)
    return service.get_monthly_analysis(year, month, include_split_parents)


# --- Alert Endpoints ---


@router.get("/alerts")
def get_current_month_alerts(
    threshold: float = Query(0.8, ge=0.0, le=1.0),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return budget alerts for the current calendar month.

    Parameters
    ----------
    threshold : float, optional
        Fraction of the budget at which an alert fires. Default is ``0.8``
        (80%). Constrained to ``[0.0, 1.0]``.

    Returns
    -------
    dict
        ``{"year": Y, "month": M, "alerts": [...]}``. Each alert has
        ``rule_id``, ``name``, ``category``, ``tags``, ``amount``, ``spent``,
        ``percentage``, and ``severity`` (``"warning"`` or ``"critical"``).
    """
    today = date.today()
    service = MonthlyBudgetService(db)
    alerts = service.get_alerts(today.year, today.month, warning_threshold=threshold)
    return {"year": today.year, "month": today.month, "alerts": alerts}


@router.get("/alerts/{year}/{month}")
def get_month_alerts(
    year: int,
    month: int,
    threshold: float = Query(0.8, ge=0.0, le=1.0),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return budget alerts for a specific calendar month.

    Parameters
    ----------
    year : int
        Calendar year.
    month : int
        Calendar month (1–12).
    threshold : float, optional
        Fraction of the budget at which an alert fires. Default is ``0.8``.

    Returns
    -------
    dict
        ``{"year": year, "month": month, "alerts": [...]}``.
    """
    service = MonthlyBudgetService(db)
    alerts = service.get_alerts(year, month, warning_threshold=threshold)
    return {"year": year, "month": month, "alerts": alerts}


# --- Yearly Budget Endpoints ---


@router.get("/yearly/{year}")
def get_yearly_view(
    year: int,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return the yearly budget view (rule rows) for a calendar year."""
    service = YearlyBudgetService(db)
    view = service.get_yearly_budget_view(year, include_split_parents)
    return {"rules": view if view else []}


@router.get("/yearly/{year}/analysis")
def get_yearly_analysis(
    year: int,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return view + computed roll-up + alerts + carry-forward report for a year."""
    return YearlyBudgetService(db).get_yearly_analysis(year, include_split_parents)


@router.post("/yearly/rules")
def create_yearly_rule(
    rule: YearlyRuleCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a yearly budget rule (409-style conflicts surface as 400)."""
    service = YearlyBudgetService(db)
    try:
        service.create_rule(rule.name, rule.amount, rule.category, rule.tags, rule.year)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/yearly/rules/{rule_id}")
def update_yearly_rule(
    rule_id: int, rule: YearlyRuleUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update a yearly budget rule."""
    service = YearlyBudgetService(db)
    updates = {k: v for k, v in rule.model_dump().items() if v is not None}
    try:
        service.update_rule(rule_id, **updates)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/yearly/rules/{rule_id}")
def delete_yearly_rule(
    rule_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a yearly budget rule."""
    YearlyBudgetService(db).delete_rule(rule_id)
    return {"status": "success"}


@router.post("/yearly/{year}/copy")
def copy_previous_year_rules(
    year: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Force-copy the latest prior year's yearly rules into ``year``.

    Unlike the auto-carry-forward used on page load, this explicit user
    action is allowed to overwrite a non-empty target year. It resolves the
    source year first — if there is no prior year with yearly rules, nothing
    is deleted (see ``YearlyBudgetService.force_copy_from_prior_year``).
    """
    service = YearlyBudgetService(db)
    result = service.force_copy_from_prior_year(year)
    if result is None:
        raise HTTPException(status_code=404, detail="No prior year rules to copy.")
    return {"status": "success", **result}


@router.get("/yearly/alerts/{year}")
def get_yearly_alerts(
    year: int,
    threshold: float = Query(0.8, ge=0.0, le=1.0),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return yearly budget alerts for a calendar year."""
    alerts = YearlyBudgetService(db).get_alerts(year, warning_threshold=threshold)
    return {"year": year, "alerts": alerts}


# --- Project Endpoints ---


@router.get("/projects")
def get_projects(
    db: Session = Depends(get_database),
) -> list[str]:
    """Get all project names."""
    service = ProjectBudgetService(db)
    return service.get_all_projects_names()


@router.get("/projects/available")
def get_available_categories_for_new_project(
    db: Session = Depends(get_database),
) -> list[str]:
    """Get available categories for a new project."""
    service = ProjectBudgetService(db)
    return service.get_available_categories_for_new_project()


@router.post("/projects")
def create_project(
    project: ProjectCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new project."""
    service = ProjectBudgetService(db)
    service.create_project(project.category, project.total_budget)
    return {"status": "success"}


@router.put("/projects/{name}")
def update_project(
    name: str, project: ProjectUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update project total budget."""
    service = ProjectBudgetService(db)
    service.update_project(name, project.total_budget)
    return {"status": "success"}


@router.delete("/projects/{name}")
def delete_project(
    name: str, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a project."""
    service = ProjectBudgetService(db)
    service.delete_project(name)
    return {"status": "success"}


@router.get("/projects/{name}")
def get_project_details(
    name: str,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get project details including rules and transactions."""
    service = ProjectBudgetService(db)
    try:
        return service.get_project_budget_view(name, include_split_parents)
    except ValueError as e:
        # Service raises ValueError when no rules exist for the project name.
        raise HTTPException(status_code=404, detail=str(e))
