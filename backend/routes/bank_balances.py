"""
Bank Balance API routes.

Provides endpoints for managing bank account balances and prior wealth.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.bank_balance_service import BankBalanceService

router = APIRouter()


class SetBalanceRequest(BaseModel):
    provider: str
    account_name: str
    balance: float


@router.get("/")
async def get_bank_balances(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all bank balance records."""
    service = BankBalanceService(db)
    return service.get_all_balances()


@router.post("/")
async def set_bank_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict:
    """Set current balance for a bank account."""
    service = BankBalanceService(db)
    return service.set_balance(
        provider=request.provider,
        account_name=request.account_name,
        balance=request.balance,
    )
