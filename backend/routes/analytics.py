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
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_overview(start_date, end_date)


@router.get("/income-outcome")
async def get_income_outcome(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    income = service.get_total_income(start_date, end_date)
    expenses = service.get_total_expenses(start_date, end_date)
    return {"total_income": income, "total_outcome": expenses, "net": income - expenses}


@router.get("/by-category")
async def get_expenses_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_expenses_by_category(start_date, end_date)


@router.get("/monthly-trend")
async def get_monthly_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database)
):
    service = AnalysisService(db)
    return service.get_monthly_trend(start_date, end_date)


@router.get("/sankey")
async def get_sankey_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database)
) -> dict:
    service = AnalysisService(db)
    return service.get_sankey_data(start_date, end_date)
