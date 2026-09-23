"""Scrape-history reads that work without the scraper stack.

``ScrapingService`` can only be imported where Playwright is installed —
it reaches the scraper adapter, which reaches Playwright. The scrape
*history* is a plain DB read with no such dependency, so it lives here
instead: the hosted demo has no Playwright, and without this split every
data source there reports "Never synced".

``ScrapingService`` delegates to this class rather than keeping a second
copy of the logic.
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import (
    ScrapingHistoryRepository,
)


class ScrapingHistoryService:
    """Read-only view over the scrape audit trail.

    Parameters
    ----------
    db : Session
        SQLAlchemy session used for both repositories.
    """

    def __init__(self, db: Session) -> None:
        self.credentials_repo = CredentialsRepository(db)
        self.scraping_history_repo = ScrapingHistoryRepository(db)

    def get_last_scrape_dates(self) -> list[dict[str, Any]]:
        """Get the last successful scrape date for every configured account.

        Returns
        -------
        list[dict[str, Any]]
            One entry per configured account, with ``service``, ``provider``,
            ``account_name`` and ``last_scrape_date`` (``None`` for an account
            that has never scraped successfully).
        """
        result = []
        for acc in self.credentials_repo.list_accounts():
            last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
                acc["service"], acc["provider"], acc["account_name"]
            )
            result.append(
                {
                    "service": acc["service"],
                    "provider": acc["provider"],
                    "account_name": acc["account_name"],
                    "last_scrape_date": last_scrape,
                }
            )
        return result
