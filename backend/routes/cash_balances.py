"""
Cash Balance API routes.

Provides endpoints for managing cash account balances and prior wealth.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.cash_balance_service import CashBalanceService

router = APIRouter()


class SetBalanceRequest(BaseModel):
    account_name: str
    balance: float


@router.get("/")
async def get_cash_balances(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all cash balance records."""
    service = CashBalanceService(db)
    return service.get_all_balances()


@router.post("/")
async def set_cash_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict:
    """Set current balance for a cash account."""
    service = CashBalanceService(db)
    return service.set_balance(
        account_name=request.account_name,
        balance=request.balance,
    )
