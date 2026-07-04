"""
Scraping API routes.

Provides endpoints to start, monitor, abort, and handle 2FA for
automated scraping of Israeli financial institutions.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import BadRequestException, EntityNotFoundException
from backend.services.scraping_service import ScrapingService

router = APIRouter()


class StartScrapingRequest(BaseModel):
    service: str
    provider: str
    account: str
    scraping_period_days: Optional[int] = Field(default=None, gt=0, le=365)
    force_2fa: bool = False


class TFAFinishRequest(BaseModel):
    service: str
    provider: str
    account: str
    code: str


class ResendTFARequest(BaseModel):
    service: str
    provider: str
    account: str


class AbortRequest(BaseModel):
    process_id: int


class StatusResponse(BaseModel):
    status: str


@router.post("/start")
def start_scraping_single(
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
        force_2fa=data.force_2fa,
    )
    return scraping_process_id


@router.post("/abort", response_model=StatusResponse)
def abort_scraping(
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
def get_scraping_status(
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


@router.post("/2fa", response_model=StatusResponse)
def handle_2fa(
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


@router.post("/resend-2fa")
async def resend_2fa(
    data: ResendTFARequest, db: Session = Depends(get_database)
) -> dict:
    """Re-issue the OTP for an awaiting scraper without losing its process.

    For providers that support in-place resend (OneZero), the same scraping
    process stays alive and a fresh SMS is sent. For providers that can't
    resend mid-flow, the service falls back to aborting and relaunching the
    scrape.

    Parameters
    ----------
    data : ResendTFARequest
        ``service``, ``provider``, and ``account`` identifying the awaiting
        scraper.

    Returns
    -------
    dict
        ``{"status": "resent", "process_id": int}`` when the code was
        re-issued in place, or ``{"status": "restarted", "process_id": int}``
        when the scrape was aborted and relaunched.

    Raises
    ------
    HTTPException
        404 if no active or 2FA-waiting scraper matches.
        400 if the resend is rate-limited (with a wait-and-retry message).
    """
    service = ScrapingService(db)
    try:
        return await service.resend_2fa_code(
            data.service, data.provider, data.account
        )
    except EntityNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/last-scrapes")
def get_last_scrapes(db: Session = Depends(get_database)) -> list:
    """Return the last successful scrape date for each configured account.

    Returns
    -------
    list[dict]
        List of records with ``service``, ``provider``, ``account``, and
        ``last_scrape_date`` fields.
    """
    service = ScrapingService(db)
    return service.get_last_scrape_dates()
