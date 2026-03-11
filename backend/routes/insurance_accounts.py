"""
Insurance Accounts API routes.

Provides a read-only endpoint for insurance account metadata
(pension, keren hishtalmut, gemel) scraped from insurance providers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.models.insurance_account import InsuranceAccount
from backend.services.investments_service import InvestmentsService

router = APIRouter()


@router.get("/")
async def get_insurance_accounts(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all insurance account metadata records.

    Returns
    -------
    list[dict]
        List of insurance account records with all fields.
    """
    rows = db.query(InsuranceAccount).all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "policy_id": r.policy_id,
            "policy_type": r.policy_type,
            "pension_type": r.pension_type,
            "account_name": r.account_name,
            "balance": r.balance,
            "balance_date": r.balance_date,
            "investment_tracks": r.investment_tracks,
            "commission_deposits_pct": r.commission_deposits_pct,
            "commission_savings_pct": r.commission_savings_pct,
            "insurance_covers": r.insurance_covers,
            "insurance_costs": r.insurance_costs,
            "liquidity_date": r.liquidity_date,
        }
        for r in rows
    ]


@router.post("/sync-investments")
async def sync_hishtalmut_investments(
    db: Session = Depends(get_database),
) -> dict:
    """Backfill investments from existing hishtalmut insurance accounts.

    Creates Investment records (with balance snapshots) for any hishtalmut
    policies that don't already have a linked investment.

    Returns
    -------
    dict
        Count of synced policies.
    """
    rows = db.query(InsuranceAccount).filter_by(policy_type="hishtalmut").all()
    inv_service = InvestmentsService(db)
    synced = 0
    for r in rows:
        meta = {
            "policy_type": r.policy_type,
            "policy_id": r.policy_id,
            "provider": r.provider,
            "account_name": r.account_name,
            "balance": r.balance,
            "balance_date": r.balance_date,
            "commission_deposits_pct": r.commission_deposits_pct,
            "commission_savings_pct": r.commission_savings_pct,
            "liquidity_date": r.liquidity_date,
        }
        inv_service.sync_from_insurance(meta)
        synced += 1
    return {"synced": synced}
