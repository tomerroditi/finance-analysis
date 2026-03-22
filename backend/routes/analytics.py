"""
Analytics API routes.

Provides endpoints for financial analysis and reporting.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.analysis_service import AnalysisService


router = APIRouter()


@router.get("/overview")
async def get_overview(
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
async def get_net_balance_over_time(
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
async def get_income_expenses_over_time(
    db: Session = Depends(get_database),
    exclude_projects: bool = False,
    exclude_liabilities: bool = False,
    exclude_refunds: bool = False,
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
    )


@router.get("/debt-payments-over-time")
async def get_debt_payments_over_time(
    db: Session = Depends(get_database),
):
    """Return monthly debt payment totals over time."""
    service = AnalysisService(db)
    return service.get_debt_payments_over_time()


@router.get("/expenses-by-category-over-time")
async def get_expenses_by_category_over_time(
    db: Session = Depends(get_database),
):
    """Return monthly expenses broken down by category."""
    service = AnalysisService(db)
    return service.get_expenses_by_category_over_time()


@router.get("/by-category")
async def get_expenses_by_category(
    db: Session = Depends(get_database),
):
    """Return expenses aggregated by category.

    Returns
    -------
    list[dict]
        List of ``{category, total}`` records sorted by total descending.
        Excludes non-expense categories (Ignore, Salary, Other Income, etc.).
    """
    service = AnalysisService(db)
    return service.get_expenses_by_category()


@router.get("/sankey")
async def get_sankey_data(
    db: Session = Depends(get_database),
) -> dict:
    """Return Sankey chart data showing income-to-expense flow.

    Returns
    -------
    dict
        ``{nodes: list[str], links: list[{source, target, value}]}`` structure
        suitable for rendering a Sankey diagram (income sources -> categories -> tags).
    """
    service = AnalysisService(db)
    return service.get_sankey_data()


@router.get("/income-by-source-over-time")
async def get_income_by_source_over_time(
    db: Session = Depends(get_database),
):
    """Return monthly income broken down by source (category+tag).

    Returns
    -------
    list[dict]
        List of ``{month, sources: {label: amount}, total}`` records
        ordered chronologically. Prior Wealth is excluded.
    """
    service = AnalysisService(db)
    return service.get_income_by_source_over_time()


@router.get("/monthly-expenses")
async def get_monthly_expenses(
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
    return service.get_monthly_expenses(exclude_pending_refunds, include_projects)


@router.get("/net-worth-over-time")
async def get_net_worth_over_time(
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
