from datetime import date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository

router = APIRouter()


class StartScrapingRequest(BaseModel):
    service: Optional[str] = None


class TFAFinishRequest(BaseModel):
    scraper_name: str
    code: str


@router.get("/history")
async def get_scraping_history(
    db: Session = Depends(get_database)
):
    """Get the scraping history from the database."""
    repo = ScrapingHistoryRepository(db)
    df = repo.get_history()
    return df.to_dict(orient="records")


@router.post("/start")
async def start_scraping(
    data: Optional[StartScrapingRequest] = None,
    db: Session = Depends(get_database)
):
    """Start scraping data from sources."""
    from backend.services.scraping_service import ScrapingService
    service = ScrapingService(db)
    service.start_scraping(service_filter=data.service if data else None)
    return {"status": "started"}


@router.get("/status")
async def get_scraping_status(
    db: Session = Depends(get_database)
):
    """Get the current scraping status."""
    from backend.services.scraping_service import ScrapingService
    service = ScrapingService(db)
    return service.get_scraping_results()


@router.post("/2fa")
async def handle_2fa(
    data: TFAFinishRequest,
    db: Session = Depends(get_database)
):
    """Submit a 2FA code."""
    from backend.services.scraping_service import ScrapingService
    service = ScrapingService(db)
    service.handle_2fa_code(data.scraper_name, data.code)
    return {"status": "success"}


@router.get("/summary")
async def get_scraping_summary(
    db: Session = Depends(get_database)
):
    """Get summary of today's scraping activity."""
    from backend.services.scraping_service import ScrapingService
    service = ScrapingService(db)
    return service.get_todays_summary()


@router.post("/clear")
async def clear_scraping_status(
    db: Session = Depends(get_database)
):
    """Clear the current scraping status."""
    from backend.services.scraping_service import ScrapingService
    service = ScrapingService(db)
    service.clear_status()
    return {"status": "cleared"}
