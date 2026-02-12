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
    service = AnalysisService(db)
    return service.get_overview(start_date, end_date)


@router.get("/net-balance-over-time")
async def get_net_balance_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    service = AnalysisService(db)
    return service.get_net_balance_over_time(start_date, end_date)


@router.get("/income-expenses-over-time")
async def get_income_expenses_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    service = AnalysisService(db)
    return service.get_income_expenses_over_time(start_date, end_date)


@router.get("/by-category")
async def get_expenses_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    service = AnalysisService(db)
    return service.get_expenses_by_category(start_date, end_date)


@router.get("/sankey")
async def get_sankey_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict:
    service = AnalysisService(db)
    return service.get_sankey_data(start_date, end_date)
