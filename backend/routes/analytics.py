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
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_overview()


@router.get("/income-outcome")
async def get_income_outcome(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    income = service.get_total_income(year, month)
    expenses = service.get_total_expenses(year, month)
    return {"total_income": income, "total_outcome": expenses, "net": income - expenses}


@router.get("/by-category")
async def get_expenses_by_category(
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_expenses_by_category()


@router.get("/monthly-trend")
async def get_monthly_trend(
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_monthly_trend()


@router.get("/sankey")
async def get_sankey_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database)
) -> dict:
    service = AnalysisService(db)
    return service.get_sankey_data(start_date, end_date)
