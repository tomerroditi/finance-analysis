"""
Bank Balance API routes.

Provides endpoints for managing bank account balances and prior wealth.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.bank_balance_service import BankBalanceService

router = APIRouter()


class SetBalanceRequest(ApiRequestModel):
    """Request body for setting a bank account's current balance."""

    provider: str
    account_name: str
    balance: float


@router.get("/")
def get_bank_balances(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all bank balance records."""
    service = BankBalanceService(db)
    return service.get_all_balances()


@router.post("/")
def set_bank_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Set current balance for a bank account.

    Raises
    ------
    ValidationException
        400 when the account has no successful scrape from today.
    """
    service = BankBalanceService(db)
    return service.set_balance(
        provider=request.provider,
        account_name=request.account_name,
        balance=request.balance,
    )
