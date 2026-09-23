"""
Insurance Accounts API routes.

Provides endpoints for insurance account metadata (pension, keren hishtalmut,
gemel) scraped from insurance providers and for syncing hishtalmut policies
to investments.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.models.insurance_account import InsuranceAccount
from backend.services.insurance_account_service import InsuranceAccountService
from backend.services.investments import InvestmentsService

router = APIRouter()


class InsuranceAccountResponse(BaseModel):
    """Response body for an insurance account record."""

    id: int
    provider: str
    policy_id: str
    policy_type: str
    pension_type: str | None = None
    account_name: str
    custom_name: str | None = None
    balance: float | None = None
    balance_date: str | None = None
    investment_tracks: str | None = None
    commission_deposits_pct: float | None = None
    commission_savings_pct: float | None = None
    insurance_covers: str | None = None
    insurance_costs: str | None = None
    liquidity_date: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ClearingHouseReportResponse(BaseModel):
    """Response body for one monthly clearing-house household summary."""

    provider: str
    account_name: str
    calc_date: str
    total_savings: float | None = None
    forecast_total_balance: float | None = None
    forecast_monthly_pension: float | None = None
    forecast_lump_sum: float | None = None
    disability_monthly: float | None = None
    survivor_spouse_monthly: float | None = None
    survivor_child_monthly: float | None = None
    death_lump_sum: float | None = None
    report_number: int | None = None
    report_count: int | None = None
    subscription_expires: str | None = None
    subscription_months_left: int | None = None
    license_holder: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InsuranceAccountRename(BaseModel):
    """Request body for renaming an insurance account."""

    custom_name: str | None = None


@router.get("/", response_model=list[InsuranceAccountResponse])
def get_insurance_accounts(
    db: Session = Depends(get_database),
) -> list[InsuranceAccount]:
    """Get all insurance account metadata records.

    Returns
    -------
    list[InsuranceAccountResponse]
        List of insurance account records with all fields.
    """
    service = InsuranceAccountService(db)
    return service.get_all()


@router.patch("/{policy_id}/rename", response_model=InsuranceAccountResponse)
def rename_insurance_account(
    policy_id: str,
    body: InsuranceAccountRename,
    db: Session = Depends(get_database),
) -> InsuranceAccount:
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


@router.get("/clearing-house-reports", response_model=list[ClearingHouseReportResponse])
def get_clearing_house_reports(
    db: Session = Depends(get_database),
) -> list[ClearingHouseReportResponse]:
    """Return the pension clearing house's monthly household summaries.

    Returns
    -------
    list[ClearingHouseReportResponse]
        One row per credential and report month, oldest first.
    """
    reports = InsuranceAccountService(db).get_clearing_house_reports()
    return [ClearingHouseReportResponse.model_validate(r) for r in reports]


@router.post("/sync-investments")
def sync_hishtalmut_investments(
    db: Session = Depends(get_database),
) -> dict[str, int]:
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
