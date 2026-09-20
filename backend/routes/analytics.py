"""
Analytics API routes.

Provides endpoints for financial analysis and reporting.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.analysis_service import AnalysisService
from backend.services.recurring_service import RecurringService
from backend.services.insights_service import InsightsService


router = APIRouter()


class RecurringDecisionRequest(BaseModel):
    """One verdict on a detected recurring-charge candidate."""

    normalized: str = Field(
        ...,
        max_length=500,
        description="Normalized merchant key, as detection reported it.",
    )
    decision: str = Field(
        ...,
        description="'confirmed', 'dismissed', or 'pending' to undo a verdict.",
    )
    # Stored beside the verdict for audit, never read back. The client
    # already has them on screen, so taking them here is free; deriving them
    # server-side would mean a full detection pass per verdict.
    label: str | None = Field(
        None, max_length=500, description="Candidate's label when the user ruled."
    )
    amount: float | None = Field(
        None, description="Candidate's median amount when the user ruled."
    )
    cadence: str | None = Field(
        None, max_length=50, description="Candidate's cadence when the user ruled."
    )


class InsightDismissalRequest(BaseModel):
    """One insight card the user waved away."""

    key: str = Field(
        ..., description="The insight's key, exactly as /insights reported it."
    )


class RecurringDecisionsRequest(BaseModel):
    """A batch of verdicts, so "confirm all" is one round trip."""

    decisions: list[RecurringDecisionRequest]


@router.get("/overview")
def get_overview(
    db: Session = Depends(get_database),
):
    """Return an aggregate financial overview across all available data.

    Returns
    -------
    dict
        Summary metrics including total income, total expenses, and net balance.
    """
    service = AnalysisService(db)
    return service.get_overview()


@router.get("/net-balance-over-time")
def get_net_balance_over_time(
    db: Session = Depends(get_database),
):
    """Return the cumulative net balance trend over time.

    Returns
    -------
    list[dict]
        List of ``{date, net_balance}`` data points ordered chronologically.
    """
    service = AnalysisService(db)
    return service.get_net_balance_over_time()


@router.get("/income-expenses-over-time")
def get_income_expenses_over_time(
    db: Session = Depends(get_database),
    exclude_projects: bool = False,
    exclude_liabilities: bool = False,
    exclude_refunds: bool = False,
    exclude_pending_refunds: bool = True,
):
    """Return monthly income and expense totals over time.

    Parameters
    ----------
    exclude_projects : bool
        If True, exclude project budget transactions.
    exclude_liabilities : bool
        If True, exclude liability/loan transactions.
    exclude_refunds : bool
        If True, only count positive income and negative expenses.
    exclude_pending_refunds : bool
        If True, a purchase still awaiting its refund is left out. Refunds
        already matched to a purchase are netted out either way.

    Returns
    -------
    list[dict]
        List of ``{month, income, expenses}`` records ordered chronologically.
    """
    service = AnalysisService(db)
    return service.get_income_expenses_over_time(
        exclude_projects=exclude_projects,
        exclude_liabilities=exclude_liabilities,
        exclude_refunds=exclude_refunds,
        exclude_pending_refunds=exclude_pending_refunds,
    )


@router.get("/debt-payments-over-time")
def get_debt_payments_over_time(
    db: Session = Depends(get_database),
):
    """Return monthly debt payment totals over time."""
    service = AnalysisService(db)
    return service.get_debt_payments_over_time()


@router.get("/expenses-by-category-over-time")
def get_expenses_by_category_over_time(
    db: Session = Depends(get_database),
    exclude_pending_refunds: bool = True,
):
    """Return monthly expenses broken down by category.

    Parameters
    ----------
    exclude_pending_refunds : bool
        If True, a purchase still awaiting its refund is left out. Refunds
        already matched to a purchase are netted against that purchase's
        category either way.
    """
    service = AnalysisService(db)
    return service.get_expenses_by_category_over_time(
        exclude_pending_refunds=exclude_pending_refunds
    )


@router.get("/by-category")
def get_expenses_by_category(
    db: Session = Depends(get_database),
    exclude_pending_refunds: bool = True,
):
    """Return expenses aggregated by category.

    Parameters
    ----------
    exclude_pending_refunds : bool
        If True, a purchase still awaiting its refund is left out. Refunds
        already matched to a purchase are netted against that purchase
        either way.

    Returns
    -------
    list[dict]
        List of ``{category, total}`` records sorted by total descending.
        Excludes non-expense categories (Ignore, Salary, Other Income, etc.).
    """
    service = AnalysisService(db)
    return service.get_expenses_by_category(
        exclude_pending_refunds=exclude_pending_refunds
    )


@router.get("/sankey")
def get_sankey_data(
    db: Session = Depends(get_database),
    exclude_pending_refunds: bool = True,
) -> dict:
    """Return Sankey chart data showing income-to-expense flow.

    Parameters
    ----------
    exclude_pending_refunds : bool
        If True, a purchase still awaiting its refund is left out. Refunds
        already matched to a purchase are netted against that purchase
        either way.

    Returns
    -------
    dict
        ``{nodes: list[str], links: list[{source, target, value}]}`` structure
        suitable for rendering a Sankey diagram (income sources -> categories -> tags).
    """
    service = AnalysisService(db)
    return service.get_sankey_data(
        exclude_pending_refunds=exclude_pending_refunds
    )


@router.get("/income-by-source-over-time")
def get_income_by_source_over_time(
    db: Session = Depends(get_database),
    exclude_pending_refunds: bool = True,
):
    """Return monthly income broken down by source (category+tag).

    Parameters
    ----------
    exclude_pending_refunds : bool
        If True, a purchase still awaiting its refund is left out. Refunds
        already matched to a purchase are netted out either way.

    Returns
    -------
    list[dict]
        List of ``{month, sources: {label: amount}, total}`` records
        ordered chronologically. Prior Wealth is excluded.
    """
    service = AnalysisService(db)
    return service.get_income_by_source_over_time(
        exclude_pending_refunds=exclude_pending_refunds
    )


@router.get("/income-by-source")
def get_income_by_source(
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_database),
) -> dict:
    """Return total income amount per source (category+tag) for a date window.

    Parameters
    ----------
    start, end : date | None
        Inclusive ``YYYY-MM-DD`` bounds. Omit both for all-time.

    Returns
    -------
    dict
        ``{sources: [{label, amount, share}], total, start, end}`` with sources
        sorted by amount descending. Prior Wealth and credit-card source are
        excluded.
    """
    service = AnalysisService(db)
    return service.get_income_by_source(start=start, end=end)


@router.get("/monthly-expenses")
def get_monthly_expenses(
    exclude_pending_refunds: bool = Query(True),
    include_projects: bool = Query(False),
    db: Session = Depends(get_database),
):
    """Return monthly expense totals and rolling averages.

    Calculates expenses using the same methodology as the monthly budget:
    split-aware, excludes non-expense categories, and optionally excludes
    pending refund transactions.

    Parameters
    ----------
    exclude_pending_refunds : bool
        When True, excludes transactions marked as pending refunds.
        Default is True.
    include_projects : bool
        When True, includes project expenses as a separate series.
        Default is False.

    Returns
    -------
    dict
        Dictionary with ``months`` list and ``avg_3_months``,
        ``avg_6_months``, ``avg_12_months`` averages.
    """
    service = AnalysisService(db)
    # The dashboard's expense KPI is a cashflow figure: a refund cancels the
    # purchase it repays whatever month it arrived in.
    return service.get_monthly_expenses(
        exclude_pending_refunds, include_projects, net_refunds=True
    )


@router.get("/recurring")
def get_recurring(
    include_dismissed: bool = Query(
        False, description="Include candidates the user dismissed."
    ),
    db: Session = Depends(get_database),
):
    """Return detected recurring-charge candidates (subscriptions, bills).

    Each item carries a ``confirmation`` verdict; only confirmed ones feed the
    budget overview, the forecast and the insight cards.

    Parameters
    ----------
    include_dismissed : bool, optional
        When True, dismissed candidates are listed too. Default False.

    Returns
    -------
    dict
        ``{items, total_monthly, pending_monthly, pending_count,
        confirmed_count, dismissed_count}``. See
        ``RecurringService.get_recurring``.
    """
    service = RecurringService(db)
    return service.get_recurring(include_dismissed=include_dismissed)


@router.post("/recurring/decisions")
def set_recurring_decisions(
    payload: RecurringDecisionsRequest,
    db: Session = Depends(get_database),
):
    """Record the user's verdicts on detected recurring-charge candidates.

    Parameters
    ----------
    payload : RecurringDecisionsRequest
        The verdicts to store.

    Returns
    -------
    dict
        ``{updated: [{normalized, decision}]}``.
    """
    service = RecurringService(db)
    return service.set_decisions(
        [entry.model_dump() for entry in payload.decisions]
    )


@router.get("/insights")
def get_insights(
    db: Session = Depends(get_database),
):
    """Return rule-based financial insight cards.

    Returns
    -------
    list[dict]
        Insight cards as ``{code, key, severity, data}``. See
        ``InsightsService.get_insights``.
    """
    service = InsightsService(db)
    return service.get_insights()


@router.post("/insights/dismiss")
def dismiss_insight(
    payload: InsightDismissalRequest,
    db: Session = Depends(get_database),
):
    """Hide one insight card.

    The dismissal is keyed to what the card is *about*, so it lapses on its
    own once that changes — next month's spike in the same category, or the
    next price change for the same subscription, is a new card.

    Parameters
    ----------
    payload : InsightDismissalRequest
        The card to hide.

    Returns
    -------
    dict
        ``{key, dismissed}``.
    """
    service = InsightsService(db)
    return service.dismiss(payload.key)


@router.post("/insights/restore")
def restore_insight(
    payload: InsightDismissalRequest,
    db: Session = Depends(get_database),
):
    """Undo a dismissal, letting the card come back.

    Parameters
    ----------
    payload : InsightDismissalRequest
        The card to bring back.

    Returns
    -------
    dict
        ``{key, dismissed}``.
    """
    service = InsightsService(db)
    return service.restore(payload.key)


@router.get("/cash-flow-forecast")
def get_cash_flow_forecast(
    db: Session = Depends(get_database),
):
    """Return the current-month cash-flow forecast.

    Combines month-to-date actuals with trend-based projection to estimate
    the month-end bank balance and the "safe to spend" figure.

    Returns
    -------
    dict
        Forecast metrics plus a ``daily`` trajectory for charting. See
        ``AnalysisService.get_cash_flow_forecast``.
    """
    service = AnalysisService(db)
    return service.get_cash_flow_forecast()


@router.get("/net-worth-over-time")
def get_net_worth_over_time(
    db: Session = Depends(get_database),
):
    """Return the net worth trend over time including investment balances.

    Returns
    -------
    list[dict]
        List of ``{date, net_worth}`` data points ordered chronologically,
        incorporating bank balances, investments, and cumulative transactions.
    """
    service = AnalysisService(db)
    return service.get_net_worth_over_time()
