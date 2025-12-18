"""
Investments API routes.

Provides endpoints for investment tracking.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.investments_repository import InvestmentsRepository

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
    include_closed: bool = False,
    db: Session = Depends(get_database)
):
    """Get all investments."""
    repo = InvestmentsRepository(db)
    df = repo.get_all_investments(include_closed=include_closed)
    return df.to_dict(orient="records")


@router.get("/{investment_id}")
async def get_investment(
    investment_id: int,
    db: Session = Depends(get_database)
):
    """Get a specific investment by ID."""
    repo = InvestmentsRepository(db)
    df = repo.get_by_id(investment_id)
    if df.empty:
        raise HTTPException(status_code=404, detail="Investment not found")
    return df.iloc[0].to_dict()


@router.post("/")
async def create_investment(
    investment: InvestmentCreate,
    db: Session = Depends(get_database)
):
    """Create a new investment."""
    repo = InvestmentsRepository(db)
    try:
        repo.create_investment(
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
            notes=investment.notes
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{investment_id}")
async def update_investment(
    investment_id: int,
    investment: InvestmentUpdate,
    db: Session = Depends(get_database)
):
    """Update an investment."""
    repo = InvestmentsRepository(db)
    try:
        updates = {k: v for k, v in investment.dict().items() if v is not None}
        repo.update_investment(investment_id, **updates)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{investment_id}/close")
async def close_investment(
    investment_id: int,
    closed_date: str,
    db: Session = Depends(get_database)
):
    """Close an investment."""
    repo = InvestmentsRepository(db)
    repo.close_investment(investment_id, closed_date)
    return {"status": "success"}


@router.post("/{investment_id}/reopen")
async def reopen_investment(
    investment_id: int,
    db: Session = Depends(get_database)
):
    """Reopen a closed investment."""
    repo = InvestmentsRepository(db)
    repo.reopen_investment(investment_id)
    return {"status": "success"}


@router.delete("/{investment_id}")
async def delete_investment(
    investment_id: int,
    db: Session = Depends(get_database)
):
    """Delete an investment."""
    repo = InvestmentsRepository(db)
    try:
        repo.delete_investment(investment_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
