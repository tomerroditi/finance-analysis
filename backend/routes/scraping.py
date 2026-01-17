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
    """Start scraping data from sources."""
    service = ScrapingService(db)
    scraping_process_id = service.start_scraping_single(
        service=data.service, provider=data.provider, account=data.account
    )
    return scraping_process_id


@router.post("/abort")
async def abort_scraping(
    data: AbortRequest, db: Session = Depends(get_database)
) -> dict:
    """Abort a scraping process."""
    service = ScrapingService(db)
    service.abort_scraping_process(data.process_id)
    return {"status": "aborted"}


@router.get("/status")
async def get_scraping_status(
    scraping_process_id: int, db: Session = Depends(get_database)
) -> dict:
    """Get the current scraping status."""
    service = ScrapingService(db)
    return service.get_scraping_status(scraping_process_id)


@router.post("/2fa")
async def handle_2fa(
    data: TFAFinishRequest, db: Session = Depends(get_database)
) -> dict:
    """Submit a 2FA code."""
    service = ScrapingService(db)
    service.submit_2fa_code(data.service, data.provider, data.account, data.code)
    return {"status": "success"}
