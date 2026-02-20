"""
Analytics API routes.

Provides endpoints for financial analysis and reporting.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.analysis_service import AnalysisService


router = APIRouter()


@router.get("/overview")
async def get_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return an aggregate financial overview for a date range.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
        Defaults to the beginning of the earliest available data.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.
        Defaults to today.

    Returns
    -------
    dict
        Summary metrics including total income, total expenses, and net balance
        for the requested period.
    """
    service = AnalysisService(db)
    return service.get_overview(start_date, end_date)


@router.get("/net-balance-over-time")
async def get_net_balance_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return the cumulative net balance trend over time.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{date, net_balance}`` data points ordered chronologically.
    """
    service = AnalysisService(db)
    return service.get_net_balance_over_time(start_date, end_date)


@router.get("/income-expenses-over-time")
async def get_income_expenses_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return monthly income and expense totals over time.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{month, income, expenses}`` records ordered chronologically.
    """
    service = AnalysisService(db)
    return service.get_income_expenses_over_time(start_date, end_date)


@router.get("/by-category")
async def get_expenses_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return expenses aggregated by category for a date range.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{category, total}`` records sorted by total descending.
        Excludes non-expense categories (Ignore, Salary, Other Income, etc.).
    """
    service = AnalysisService(db)
    return service.get_expenses_by_category(start_date, end_date)


@router.get("/sankey")
async def get_sankey_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict:
    """Return Sankey chart data showing income-to-expense flow.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    dict
        ``{nodes: list[str], links: list[{source, target, value}]}`` structure
        suitable for rendering a Sankey diagram (income sources -> categories -> tags).
    """
    service = AnalysisService(db)
    return service.get_sankey_data(start_date, end_date)


@router.get("/income-by-source-over-time")
async def get_income_by_source_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return monthly income broken down by source (category+tag).

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{month, sources: {label: amount}, total}`` records
        ordered chronologically. Prior Wealth is excluded.
    """
    service = AnalysisService(db)
    return service.get_income_by_source_over_time(start_date, end_date)


@router.get("/net-worth-over-time")
async def get_net_worth_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return the net worth trend over time including investment balances.

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{date, net_worth}`` data points ordered chronologically,
        incorporating bank balances, investments, and cumulative transactions.
    """
    service = AnalysisService(db)
    return service.get_net_worth_over_time(start_date, end_date)
