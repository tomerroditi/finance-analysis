"""
Interest rates API routes.

Exposes the Bank of Israel key-rate series (and derived prime) used to
price prime-based loan types.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.rates_service import RatesService

router = APIRouter()


@router.get("/current")
def get_current_rates(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Return the latest known BoI key rate and derived prime rate."""
    service = RatesService(db)
    return service.get_current()


@router.get("/history")
def get_rate_history(
    series: str = "boi_rate", db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return the step-point history of a rate series.

    Parameters
    ----------
    series : str, optional
        ``boi_rate`` (default) or ``prime``.
    """
    service = RatesService(db)
    return service.get_history(series)


@router.post("/refresh")
def refresh_rates(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Fetch the current key rate from the BoI public API.

    Never fails on network errors — returns ``status: unavailable``
    with the last known rates instead.
    """
    service = RatesService(db)
    return service.refresh_from_boi()
