"""
Insurance Accounts API routes.

Provides endpoints for insurance account metadata (pension, keren hishtalmut,
gemel) scraped from insurance providers and for syncing hishtalmut policies
to investments.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.insurance_account_service import InsuranceAccountService
from backend.services.investments_service import InvestmentsService

router = APIRouter()


class InsuranceAccountResponse(BaseModel):
    """Response body for an insurance account record."""

    id: int
    provider: str
    policy_id: str
    policy_type: str
    pension_type: Optional[str] = None
    account_name: str
    custom_name: Optional[str] = None
    balance: Optional[float] = None
    balance_date: Optional[str] = None
    investment_tracks: Optional[str] = None
    commission_deposits_pct: Optional[float] = None
    commission_savings_pct: Optional[float] = None
    insurance_covers: Optional[str] = None
    insurance_costs: Optional[str] = None
    liquidity_date: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InsuranceAccountRename(BaseModel):
    """Request body for renaming an insurance account."""

    custom_name: Optional[str] = None


@router.get("/", response_model=list[InsuranceAccountResponse])
async def get_insurance_accounts(
    db: Session = Depends(get_database),
):
    """Get all insurance account metadata records.

    Returns
    -------
    list[InsuranceAccountResponse]
        List of insurance account records with all fields.
    """
    service = InsuranceAccountService(db)
    return service.get_all()


@router.patch("/{policy_id}/rename", response_model=InsuranceAccountResponse)
async def rename_insurance_account(
    policy_id: str,
    body: InsuranceAccountRename,
    db: Session = Depends(get_database),
):
    """Set or clear the user-defined display name for an insurance account.

    The override persists across scrapes. For ``hishtalmut`` policies, the
    linked Investment's ``name`` is updated in lockstep so the Investments page
    reflects the change immediately.

    Parameters
    ----------
    policy_id : str
        Policy identifier of the account to rename.
    body : InsuranceAccountRename
        ``custom_name`` is the new display name. Send ``null`` or an empty
        string to clear the override.
    """
    return InsuranceAccountService(db).rename(policy_id, body.custom_name)


@router.post("/sync-investments")
async def sync_hishtalmut_investments(
    db: Session = Depends(get_database),
) -> dict:
    """Backfill investments from existing hishtalmut insurance accounts.

    Creates or updates Investment records (with balance snapshots) for all
    hishtalmut policies. Idempotent — safe to re-run.

    Returns
    -------
    dict
        Count of hishtalmut policies processed.
    """
    processed = InvestmentsService(db).backfill_from_insurance_accounts()
    return {"synced": processed}
