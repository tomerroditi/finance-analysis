"""
Scraping API routes.

Provides endpoints to start, monitor, abort, and handle 2FA for
automated scraping of Israeli financial institutions.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.scraping_service import ScrapingService

router = APIRouter()


class StartScrapingRequest(BaseModel):
    service: str
    provider: str
    account: str
    scraping_period_days: Optional[int] = None


class TFAFinishRequest(BaseModel):
    service: str
    provider: str
    account: str
    code: str


class AbortRequest(BaseModel):
    process_id: int


@router.post("/start")
async def start_scraping_single(
    data: StartScrapingRequest, db: Session = Depends(get_database)
) -> int:
    """Start a scraping job for a single account.

    Launches the scraper in a background thread. The returned process ID
    can be used to poll status or submit a 2FA code.

    Parameters
    ----------
    data : StartScrapingRequest
        ``service`` (e.g. ``credit_cards``, ``banks``), ``provider``
        (e.g. ``hapoalim``), and ``account`` name identifying which account
        to scrape.

    Returns
    -------
    int
        Scraping process ID used to query status or handle 2FA.
    """
    service = ScrapingService(db)
    scraping_process_id = service.start_scraping_single(
        service=data.service,
        provider=data.provider,
        account=data.account,
        scraping_period_days=data.scraping_period_days,
    )
    return scraping_process_id


@router.post("/abort")
async def abort_scraping(
    data: AbortRequest, db: Session = Depends(get_database)
) -> dict:
    """Abort a running scraping process.

    Parameters
    ----------
    data : AbortRequest
        ``process_id`` of the scraping job to abort.

    Returns
    -------
    dict
        ``{"status": "aborted"}`` on success.
    """
    service = ScrapingService(db)
    service.abort_scraping_process(data.process_id)
    return {"status": "aborted"}


@router.get("/status")
async def get_scraping_status(
    scraping_process_id: int, db: Session = Depends(get_database)
) -> dict:
    """Return the current status of a scraping job.

    Parameters
    ----------
    scraping_process_id : int
        ID returned by the ``/start`` endpoint.

    Returns
    -------
    dict
        Status dict including ``status`` (e.g. ``running``, ``done``,
        ``failed``), and optionally ``requires_2fa`` and error details.
    """
    service = ScrapingService(db)
    return service.get_scraping_status(scraping_process_id)


@router.post("/2fa")
async def handle_2fa(
    data: TFAFinishRequest, db: Session = Depends(get_database)
) -> dict:
    """Submit a 2FA OTP code to unblock a waiting scraping job.

    Parameters
    ----------
    data : TFAFinishRequest
        ``service``, ``provider``, ``account`` identifying the scraper, and
        ``code`` — the OTP received by the user. Pass ``"cancel"`` as the
        code to abort the scraping process.

    Returns
    -------
    dict
        ``{"status": "success"}`` when the code is forwarded successfully.
    """
    service = ScrapingService(db)
    service.submit_2fa_code(data.service, data.provider, data.account, data.code)
    return {"status": "success"}


@router.get("/last-scrapes")
async def get_last_scrapes(db: Session = Depends(get_database)) -> list:
    """Return the last successful scrape date for each configured account.

    Returns
    -------
    list[dict]
        List of records with ``service``, ``provider``, ``account``, and
        ``last_scrape_date`` fields.
    """
    service = ScrapingService(db)
    return service.get_last_scrape_dates()
