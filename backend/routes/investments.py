"""
Investments API routes.

Provides endpoints for investment tracking.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.investments_service import InvestmentsService

router = APIRouter()


class InvestmentCreate(BaseModel):
    category: str
    tag: str
    type: str
    name: str
    interest_rate: Optional[float] = None
    interest_rate_type: str = "fixed"
    commission_deposit: Optional[float] = None
    commission_management: Optional[float] = None
    commission_withdrawal: Optional[float] = None
    liquidity_date: Optional[str] = None
    maturity_date: Optional[str] = None
    notes: Optional[str] = None


class InvestmentUpdate(BaseModel):
    name: Optional[str] = None
    interest_rate: Optional[float] = None
    interest_rate_type: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def get_investments(
    include_closed: bool = False, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Get all investments."""
    service = InvestmentsService(db)
    return service.get_all_investments(include_closed=include_closed)


@router.get("/{investment_id}")
async def get_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Get a specific investment by ID."""
    service = InvestmentsService(db)
    return service.get_investment(investment_id)


@router.get("/analysis/portfolio")
async def get_portfolio_analysis(
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get portfolio-level analysis and metrics."""
    service = InvestmentsService(db)
    return service.get_portfolio_overview()


@router.get("/{investment_id}/analysis")
async def get_investment_analysis(
    investment_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get detailed analysis for a specific investment."""
    service = InvestmentsService(db)
    return service.get_investment_analysis(investment_id, start_date, end_date)


@router.post("/")
async def create_investment(
    investment: InvestmentCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new investment."""
    service = InvestmentsService(db)
    service.create_investment(
        category=investment.category,
        tag=investment.tag,
        type_=investment.type,
        name=investment.name,
        interest_rate=investment.interest_rate,
        interest_rate_type=investment.interest_rate_type,
        commission_deposit=investment.commission_deposit,
        commission_management=investment.commission_management,
        commission_withdrawal=investment.commission_withdrawal,
        liquidity_date=investment.liquidity_date,
        maturity_date=investment.maturity_date,
        notes=investment.notes,
    )
    return {"status": "success"}


@router.put("/{investment_id}")
async def update_investment(
    investment_id: int,
    investment: InvestmentUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update an investment."""
    service = InvestmentsService(db)
    updates = {k: v for k, v in investment.dict().items() if v is not None}
    service.update_investment(investment_id, **updates)
    return {"status": "success"}


@router.post("/{investment_id}/close")
async def close_investment(
    investment_id: int, closed_date: str, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Close an investment."""
    service = InvestmentsService(db)
    service.close_investment(investment_id, closed_date)
    return {"status": "success"}


@router.post("/{investment_id}/reopen")
async def reopen_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Reopen a closed investment."""
    service = InvestmentsService(db)
    service.reopen_investment(investment_id)
    return {"status": "success"}


@router.delete("/{investment_id}")
async def delete_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete an investment."""
    service = InvestmentsService(db)
    service.delete_investment(investment_id)
    return {"status": "success"}
