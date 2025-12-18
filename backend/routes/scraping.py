"""
Scraping API routes.

Provides endpoints for data scraping operations.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository

router = APIRouter()


class TwoFactorCode(BaseModel):
    scraper_name: str
    code: str


@router.get("/history")
async def get_scraping_history(
    db: Session = Depends(get_database)
):
    """Get the complete scraping history."""
    repo = ScrapingHistoryRepository(db)
    df = repo.get_scraping_history()
    return df.to_dict(orient="records")


@router.get("/today")
async def get_todays_summary(
    db: Session = Depends(get_database)
):
    """Get summary of today's scraping activity."""
    repo = ScrapingHistoryRepository(db)
    return repo.get_todays_scraping_summary()


@router.post("/start")
async def start_scraping():
    """
    Start scraping for all configured accounts.
    
    Note: This is a placeholder - actual scraping logic requires
    integration with the scraping service which manages Node.js processes.
    """
    # TODO: Implement scraping service integration
    return {
        "status": "not_implemented",
        "message": "Scraping service integration pending"
    }


@router.post("/2fa")
async def submit_2fa_code(data: TwoFactorCode):
    """
    Submit 2FA code for a waiting scraper.
    
    Note: This is a placeholder - actual 2FA handling requires
    integration with the scraping service.
    """
    # TODO: Implement 2FA handling
    return {
        "status": "not_implemented",
        "message": "2FA handling pending integration"
    }


@router.get("/waiting-2fa")
async def get_waiting_2fa_scrapers():
    """
    Get list of scrapers waiting for 2FA input.
    
    Note: This is a placeholder - actual state is managed by scraping service.
    """
    return {"waiting": []}
