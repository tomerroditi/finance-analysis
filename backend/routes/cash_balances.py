"""
Cash Balance API routes.

Provides endpoints for managing cash account balances and prior wealth.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.cash_balance_service import CashBalanceService

router = APIRouter()


class SetBalanceRequest(ApiRequestModel):
    """Request body for setting a cash envelope's current balance."""

    account_name: str
    balance: float


@router.get("/")
def get_cash_balances(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all cash balance records."""
    service = CashBalanceService(db)
    return service.get_all_balances()


@router.post("/")
def set_cash_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Set current balance for a cash account.

    Raises
    ------
    ValidationException
        400 when the balance is negative.
    """
    return CashBalanceService(db).set_balance(
        account_name=request.account_name,
        balance=request.balance,
    )


@router.post("/migrate")
def migrate_cash_balances(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Migrate existing cash transactions to cash_balances table.

    Idempotent: skips accounts that are already migrated.
    Deletes the old synthetic 'Prior Wealth' transaction.
    """
    service = CashBalanceService(db)
    return service.migrate_from_transactions()


@router.delete("/{account_name}")
def delete_cash_balance(
    account_name: str,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Delete a cash balance record by account name.

    Migrates any transactions from the deleted account to "Wallet".
    Cannot delete the default "Wallet" account.

    Raises
    ------
    EntityNotFoundException
        404 if no cash balance record exists for ``account_name``.
    ValidationException
        400 when the account cannot be deleted (the default "Wallet").
    """
    CashBalanceService(db).delete_for_account(account_name)
    return {"status": "deleted", "account_name": account_name}
