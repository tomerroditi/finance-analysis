"""
Budget API routes.

Provides endpoints for budget rule management, analysis, and project management.
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import EntityNotFoundException
from backend.routes.schemas import (
    MAX_YEAR,
    MIN_YEAR,
    ApiRequestModel,
    MonthPath,
    YearPath,
)
from backend.services.budget import (
    BudgetOverviewService,
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
    YearlyBudgetService,
)

router = APIRouter()


class BudgetRuleCreate(ApiRequestModel):
    """Request body for creating a monthly or project budget rule."""

    name: str
    amount: float
    category: str
    tags: str | list[str]
    month: int | None = Field(None, ge=1, le=12)
    year: int | None = Field(None, ge=MIN_YEAR, le=MAX_YEAR)

    @model_validator(mode="after")
    def _month_and_year_together(self) -> "BudgetRuleCreate":
        """Require ``month`` and ``year`` together (monthly) or neither (project).

        ``year`` alone would mint a yearly row through the monthly endpoint
        (bypassing the yearly service's validation), and ``month`` alone a
        monthly row with no year.
        """
        if (self.month is None) != (self.year is None):
            raise ValueError("month and year must be given together")
        return self


class BudgetRuleUpdate(ApiRequestModel):
    """Partial update of a monthly or project rule; ``None`` fields are kept."""

    name: str | None = None
    amount: float | None = None
    category: str | None = None
    tags: str | list[str] | None = None


class YearlyRuleCreate(ApiRequestModel):
    """Request body for creating a yearly budget rule."""

    name: str
    amount: float
    category: str
    tags: str | list[str]
    year: int = Field(ge=MIN_YEAR, le=MAX_YEAR)


class YearlyRuleUpdate(ApiRequestModel):
    """Partial update of a yearly rule; ``None`` fields are kept."""

    name: str | None = None
    amount: float | None = None
    category: str | None = None
    tags: str | list[str] | None = None


class YearlyRuleClosedUpdate(ApiRequestModel):
    """Request body for closing or reopening a yearly envelope."""

    closed: bool


class ProjectCreate(ApiRequestModel):
    """Request body for creating a project budget."""

    category: str
    total_budget: float


class ProjectUpdate(ApiRequestModel):
    """Request body for changing a project's total budget."""

    total_budget: float


class ProjectClosedUpdate(ApiRequestModel):
    """Request body for closing or reopening a project."""

    closed: bool


@router.get("/rules")
def get_budget_rules(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all budget rules."""
    service = BudgetService(db)
    df = service.get_all_rules()
    return df.to_dict(orient="records")


@router.get("/rules/{year}/{month}")
def get_budget_rules_by_month(
    year: int = YearPath,
    month: int = MonthPath,
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
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
    service.create_rule(
        rule.name, rule.amount, rule.category, rule.tags, rule.month, rule.year
    )
    return {"status": "success"}


@router.put("/rules/{rule_id}")
def update_budget_rule(
    rule_id: int, rule: BudgetRuleUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update a budget rule.

    This route is shared between monthly and project rules (both are edited
    through the same ``rule_id``), so it uses ``MonthlyBudgetService`` — its
    ``update_rule`` override guards monthly edits against claiming a
    yearly-owned or project-owned tag/category, and guards project edits
    against claiming a category already used by a monthly/yearly budget. It
    is a no-op passthrough only when the edit doesn't touch category/tags.
    """
    service = MonthlyBudgetService(db)
    updates = {k: v for k, v in rule.model_dump().items() if v is not None}
    service.update_rule(rule_id, **updates)
    return {"status": "success"}


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
    year: int = YearPath,
    month: int = MonthPath,
    db: Session = Depends(get_database),
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
    EntityNotFoundException
        404 if the previous month has no rules to copy.
    """
    result = MonthlyBudgetService(db).copy_last_month_rules(year, month)
    if result is None:
        raise EntityNotFoundException("No rules found in the previous month to copy.")
    return {"status": "success", "message": result}


@router.get("/analysis/{year}/{month}")
def get_monthly_analysis(
    year: int = YearPath,
    month: int = MonthPath,
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


@router.get("/trend/{year}/{month}")
def get_budget_trend(
    year: int = YearPath,
    month: int = MonthPath,
    months: int = Query(12, ge=1, le=36),
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Return budget-vs-actual totals for the trailing ``months`` months.

    One request in place of the per-month analysis call the budget
    sparkline used to make for each point.

    Read-only: unlike ``/analysis/{year}/{month}`` this never auto-fills an
    empty month, so the last point reports zeros for a month whose rules
    have not been created yet. The caller is displaying that month and holds
    its analysis already, so the frontend overlays it from there.

    Parameters
    ----------
    year : int
        Year of the last month in the series.
    month : int
        Month (1-12) of the last month in the series, inclusive.
    months : int, optional
        How many calendar months the series spans. Defaults to 12.
    include_split_parents : bool, optional
        When ``True``, include split parents alongside their children.

    Returns
    -------
    list[dict]
        One entry per month, oldest first, with ``year``, ``month``,
        ``budget``, ``actual``, a ``rules`` name-to-spend mapping and a
        ``limits`` name-to-cap mapping for that month.
    """
    service = MonthlyBudgetService(db)
    return service.get_budget_trend(year, month, months, include_split_parents)


@router.get("/overview/{year}/{month}")
def get_budget_overview(
    year: int = Path(ge=1900, le=2999),
    month: int = MonthPath,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return one month read across monthly, yearly and project budgets.

    Carries the two facts no other endpoint exposes: the split of the month's
    monthly-pool spend into recurring and day-to-day, with the recurring charges
    still due before month end; and, per yearly or project envelope, what this
    month contributed alongside where that envelope stands overall.

    Parameters
    ----------
    year : int
        Calendar year of the month to summarise.
    month : int
        Calendar month. Bounded at the route rather than left open like the
        sibling analysis endpoints: this one sizes the month with
        ``calendar.monthrange``, which raises on anything outside 1-12, so an
        unbounded parameter turns a bad request into a 500.
    include_split_parents : bool, optional
        When ``True``, include the original parent transactions of splits
        alongside the individual split rows. Defaults to ``False``.

    Returns
    -------
    dict
        See :meth:`BudgetOverviewService.get_overview` for the full shape.
    """
    return BudgetOverviewService(db).get_overview(year, month, include_split_parents)


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
    return MonthlyBudgetService(db).get_current_month_alerts(
        warning_threshold=threshold
    )


@router.get("/alerts/{year}/{month}")
def get_month_alerts(
    year: int = YearPath,
    month: int = MonthPath,
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


@router.get("/yearly/{year}")
def get_yearly_view(
    year: int = YearPath,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return the yearly budget view (rule rows) for a calendar year."""
    service = YearlyBudgetService(db)
    view = service.get_yearly_budget_view(year, include_split_parents)
    return {"rules": view or []}


@router.get("/yearly/{year}/analysis")
def get_yearly_analysis(
    year: int = YearPath,
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
    YearlyBudgetService(db).create_rule(
        rule.name, rule.amount, rule.category, rule.tags, rule.year
    )
    return {"status": "success"}


@router.put("/yearly/rules/{rule_id}")
def update_yearly_rule(
    rule_id: int, rule: YearlyRuleUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update a yearly budget rule."""
    updates = {k: v for k, v in rule.model_dump().items() if v is not None}
    YearlyBudgetService(db).update_rule(rule_id, **updates)
    return {"status": "success"}


@router.put("/yearly/rules/{rule_id}/closed")
def set_yearly_rule_closed(
    rule_id: int,
    body: YearlyRuleClosedUpdate,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Close a settled yearly envelope, or reopen a closed one.

    A closed rule keeps its allocation, its spend and its row in the year's
    tab, and goes on claiming its tags against monthly rules; it only stops
    appearing in the budget Overview.

    Raises
    ------
    EntityNotFoundException
        404 if ``rule_id`` is not a yearly rule.
    """
    YearlyBudgetService(db).set_rule_closed(rule_id, body.closed)
    return {"status": "success", "id": rule_id, "closed": body.closed}


@router.delete("/yearly/rules/{rule_id}")
def delete_yearly_rule(
    rule_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a yearly budget rule."""
    YearlyBudgetService(db).delete_rule(rule_id)
    return {"status": "success"}


@router.post("/yearly/{year}/copy")
def copy_previous_year_rules(
    year: int = YearPath, db: Session = Depends(get_database)
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
        raise EntityNotFoundException("No prior year rules to copy.")
    return {"status": "success", **result}


@router.get("/yearly/alerts/{year}")
def get_yearly_alerts(
    year: int = YearPath,
    threshold: float = Query(0.8, ge=0.0, le=1.0),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return yearly budget alerts for a calendar year."""
    alerts = YearlyBudgetService(db).get_alerts(year, warning_threshold=threshold)
    return {"year": year, "alerts": alerts}


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


@router.get("/projects/status")
def get_projects_status(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get every project with its closed flag.

    Declared above ``/projects/{name}`` so the literal path wins the match.
    """
    service = ProjectBudgetService(db)
    return service.get_projects_status()


@router.post("/projects")
def create_project(
    project: ProjectCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new project."""
    ProjectBudgetService(db).create_project(project.category, project.total_budget)
    return {"status": "success"}


@router.get("/category-conflicts")
def get_category_conflicts(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Categories currently in BOTH a project and a monthly/yearly budget."""
    return {"conflicts": BudgetService(db).find_category_overlaps()}


@router.put("/projects/{name}")
def update_project(
    name: str, project: ProjectUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update project total budget.

    Raises
    ------
    EntityNotFoundException
        404 if no project with ``name`` exists.
    """
    ProjectBudgetService(db).update_project(name, project.total_budget)
    return {"status": "success"}


@router.put("/projects/{name}/closed")
def set_project_closed(
    name: str, body: ProjectClosedUpdate, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Close a finished project, or reopen a closed one.

    A closed project keeps every rule and transaction; it only stops appearing
    in the budget Overview.

    Raises
    ------
    EntityNotFoundException
        404 if no project with ``name`` exists.
    """
    ProjectBudgetService(db).set_project_closed(name, body.closed)
    return {"status": "success", "name": name, "closed": body.closed}


@router.delete("/projects/{name}")
def delete_project(name: str, db: Session = Depends(get_database)) -> dict[str, str]:
    """Delete a project.

    Raises
    ------
    EntityNotFoundException
        404 if no project with ``name`` exists.
    """
    ProjectBudgetService(db).delete_project(name)
    return {"status": "success"}


@router.get("/projects/{name}")
def get_project_details(
    name: str,
    include_split_parents: bool = Query(False),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get project details including rules and transactions."""
    return ProjectBudgetService(db).get_project_budget_view(name, include_split_parents)
