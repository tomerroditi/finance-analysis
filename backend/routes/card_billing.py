"""
Card billing API routes.

When each connected credit card bills, and which bank account pays it.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.card_billing_service import CardBillingService

router = APIRouter()


@router.get("/")
def get_card_billing(db: Session = Depends(get_database)) -> list[dict[str, Any]]:
    """Return every card login's cards with their billing day and paying account."""
    return CardBillingService(db).get_all()
