"""
Liabilities API routes.

Provides endpoints for liability (loan/debt) tracking.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.liabilities_service import LiabilitiesService

router = APIRouter()


class LiabilityCreate(BaseModel):
    name: str
    tag: str
    principal_amount: float
    interest_rate: float
    term_months: int
    start_date: str
    lender: Optional[str] = None
    notes: Optional[str] = None


class LiabilityUpdate(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    interest_rate: Optional[float] = None
    paid_off_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def get_liabilities(
    include_paid_off: bool = False, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return all liability records.

    Parameters
    ----------
    include_paid_off : bool, optional
        When ``True``, include liabilities that have been paid off.
        Defaults to ``False`` (active liabilities only).
    """
    service = LiabilitiesService(db)
    return service.get_all_liabilities(include_paid_off=include_paid_off)


@router.get("/detect-transactions")
async def detect_tag_transactions(
    tag: str, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Detect existing transactions for a liability tag.

    Returns receipt info (date, amount) and payment list to help
    auto-populate the create form.
    """
    service = LiabilitiesService(db)
    return service.detect_tag_transactions(tag)


@router.get("/{liability_id}/analysis")
async def get_liability_analysis(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return detailed analysis for a specific liability."""
    service = LiabilitiesService(db)
    return service.get_liability_analysis(liability_id)


@router.get("/{liability_id}/transactions")
async def get_liability_transactions(
    liability_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return all transactions associated with a specific liability."""
    service = LiabilitiesService(db)
    return service.get_liability_transactions(liability_id)


@router.get("/{liability_id}")
async def get_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Get a specific liability by ID."""
    service = LiabilitiesService(db)
    return service.get_liability(liability_id)


@router.post("/")
async def create_liability(
    liability: LiabilityCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new liability."""
    service = LiabilitiesService(db)
    service.create_liability(
        name=liability.name,
        tag=liability.tag,
        principal_amount=liability.principal_amount,
        interest_rate=liability.interest_rate,
        term_months=liability.term_months,
        start_date=liability.start_date,
        lender=liability.lender,
        notes=liability.notes,
    )
    return {"status": "success"}


@router.put("/{liability_id}")
async def update_liability(
    liability_id: int,
    liability: LiabilityUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update a liability."""
    service = LiabilitiesService(db)
    updates = {k: v for k, v in liability.model_dump().items() if v is not None}
    service.update_liability(liability_id, **updates)
    return {"status": "success"}


@router.post("/{liability_id}/pay-off")
async def pay_off_liability(
    liability_id: int, paid_off_date: str, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Mark a liability as paid off.

    Parameters
    ----------
    liability_id : int
        ID of the liability to pay off.
    paid_off_date : str
        ISO date string (YYYY-MM-DD) recording when the liability was paid off.
    """
    service = LiabilitiesService(db)
    service.mark_paid_off(liability_id, paid_off_date)
    return {"status": "success"}


@router.post("/{liability_id}/reopen")
async def reopen_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Reopen a paid-off liability."""
    service = LiabilitiesService(db)
    service.reopen(liability_id)
    return {"status": "success"}


@router.post("/{liability_id}/generate-transactions")
async def generate_missing_transactions(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Auto-generate missing payment transactions from amortization schedule."""
    service = LiabilitiesService(db)
    created = service.generate_missing_transactions(liability_id)
    return {"status": "success", "transactions_created": created}


@router.delete("/{liability_id}")
async def delete_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a liability."""
    service = LiabilitiesService(db)
    service.delete_liability(liability_id)
    return {"status": "success"}
