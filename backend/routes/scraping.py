from datetime import date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.services.scraping_service import ScrapingService
from backend.dependencies import get_database
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
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


@router.post("/start")
async def start_scraping_single(
    data: StartScrapingRequest,
    db: Session = Depends(get_database)
) -> int:
    """Start scraping data from sources."""
    service = ScrapingService(db)
    scraping_process_id = service.start_scraping_single(
        service=data.service,
        provider=data.provider,
        account=data.account
    )
    return scraping_process_id


@router.get("/status")
async def get_scraping_status(
    scraping_process_id: str,
    db: Session = Depends(get_database)
) -> str:
    """Get the current scraping status."""
    service = ScrapingService(db)
    return service.get_scraping_status(scraping_process_id)


@router.post("/2fa")
async def handle_2fa(
    data: TFAFinishRequest,
    db: Session = Depends(get_database)
) -> dict:
    """Submit a 2FA code."""
    service = ScrapingService(db)
    service.handle_2fa_code(data.service, data.provider, data.account, data.code)
    return {"status": "success"}

