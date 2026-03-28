"""
Insurance Accounts API routes.

Provides a read-only endpoint for insurance account metadata
(pension, keren hishtalmut, gemel) scraped from insurance providers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.insurance_account_service import InsuranceAccountService

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
    service = InsuranceAccountService(db)
    return service.get_all()
