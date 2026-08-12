"""Read-only scrape-history queries, deliberately free of the scraper stack.

Split out of ``ScrapingService`` because that module imports the scraper
framework (Playwright, the provider classes, the live-adapter registries) at
module level. Serverless deployments omit Playwright entirely, so importing
``ScrapingService`` there fails — and with it went the one piece of scrape data
the UI needs even when scraping is impossible: when each account last synced.

Nothing here touches a scraper, a browser or the OS keyring. ``ScrapingService``
delegates to it so there is exactly one implementation.
"""

from typing import Dict, List

from sqlalchemy.orm import Session

from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository


class ScrapingHistoryService:
    """Queries over recorded scrape history for the configured accounts."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository(db)

    def get_last_scrape_dates(self) -> List[Dict]:
        """Last successful scrape date for every configured account.

        Returns
        -------
        list[dict]
            One record per configured account with ``service``, ``provider``,
            ``account_name`` and ``last_scrape_date`` (None when the account
            has never scraped successfully).
        """
        accounts = self.credentials_repo.list_accounts()
        return [
            {
                "service": acc["service"],
                "provider": acc["provider"],
                "account_name": acc["account_name"],
                "last_scrape_date": (
                    self.scraping_history_repo.get_last_successful_scrape_date(
                        acc["service"], acc["provider"], acc["account_name"]
                    )
                ),
            }
            for acc in accounts
        ]
