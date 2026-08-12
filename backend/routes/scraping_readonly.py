"""Scrape-history routes that work without the scraper stack.

Mounted under ``/api/scraping`` alongside (or, on serverless, instead of)
``routes/scraping.py``. That module can only be imported where Playwright is
installed; these endpoints only read the history table, so they stay available
on the hosted demo — which is the difference between a Data Sources page that
shows when each source last synced and one where every card claims it has
never synced.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.scraping_history_service import ScrapingHistoryService

router = APIRouter()


@router.get("/last-scrapes")
def get_last_scrapes(db: Session = Depends(get_database)) -> list:
    """Return the last successful scrape date for each configured account.

    Returns
    -------
    list[dict]
        List of records with ``service``, ``provider``, ``account_name``, and
        ``last_scrape_date`` fields.
    """
    return ScrapingHistoryService(db).get_last_scrape_dates()
