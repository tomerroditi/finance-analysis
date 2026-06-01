"""
Onboarding API routes.

Exposes a single read-only status endpoint the frontend hits on mount to
decide whether to route the user to the onboarding wizard or to the
dashboard.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.onboarding_service import OnboardingService

router = APIRouter()


class OnboardingStatus(BaseModel):
    """Onboarding status flags for a given database.

    Each flag is intentionally coarse (bool, not count) so the response is
    safe to cache and free of PII. ``is_first_run`` is a derived
    convenience flag — it is true exactly when the other flags are all
    false.
    """

    has_credentials: bool
    has_transactions: bool
    has_budgets: bool
    has_investments: bool
    is_first_run: bool


@router.get("/status", response_model=OnboardingStatus)
async def get_onboarding_status(
    db: Session = Depends(get_database),
) -> OnboardingStatus:
    """Return whether the active database has been populated yet."""
    service = OnboardingService(db)
    return OnboardingStatus(**service.get_status())
