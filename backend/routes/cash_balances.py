"""
Cash Balance API routes.

Provides endpoints for managing cash account balances and prior wealth.
"""

from fastapi import APIRouter, Depends, HTTPException
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
    try:
        return service.set_balance(
            account_name=request.account_name,
            balance=request.balance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/migrate")
async def migrate_cash_balances(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Migrate existing cash transactions to cash_balances table.

    Idempotent: skips accounts that are already migrated.
    Deletes the old synthetic 'Prior Wealth' transaction.
    """
    service = CashBalanceService(db)
    return service.migrate_from_transactions()


@router.delete("/{account_name}")
async def delete_cash_balance(
    account_name: str,
    db: Session = Depends(get_database),
) -> dict:
    """Delete a cash balance record by account name.

    Migrates any transactions from the deleted account to "Wallet".
    Cannot delete the default "Wallet" account.
    """
    service = CashBalanceService(db)
    try:
        service.delete_for_account(account_name)
        return {"status": "deleted", "account_name": account_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
