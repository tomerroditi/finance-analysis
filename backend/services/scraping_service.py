from datetime import date, datetime, timedelta
from threading import Thread
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from backend.database import get_db_context
from backend.errors import EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.scraper import Scraper, get_scraper, is_2fa_required

_tfa_scrapers_waiting: Dict[str, Tuple[Scraper, Thread]] = {}


class ScrapingService:
    """
    Service for managing data scraping operations.
    Handles background threads and 2FA wait states.
    """

    def __init__(self, db: Session):
        self.db = db
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository(db)

    def get_scraping_status(self, scraping_process_id: int) -> Dict[str, str | int]:
        """Get the current scraping status."""
        status = self.scraping_history_repo.get_scraping_status(
            int(scraping_process_id)
        )
        error_message = self.scraping_history_repo.get_error_message(
            int(scraping_process_id)
        )
        return {
            "status": status or "unknown",
            "process_id": scraping_process_id,
            "error_message": error_message,
        }

    def get_last_scrape_dates(self) -> List[Dict]:
        """
        Get last successful scrape dates for all configured accounts.
        Returns a list of dicts with service, provider, account_name, and last_scrape_date.
        """
        accounts = self.credentials_repo.list_accounts()
        result = []
        for acc in accounts:
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

    def start_scraping(self, accounts: List[Dict]) -> None:
        """
        Start the scraping process for multiple accounts.
        """
        for account in accounts:
            self.start_scraping_single(
                account["service"], account["provider"], account["account"]
            )

    def start_scraping_single(self, service: str, provider: str, account: str) -> int:
        """
        Start the scraping process for a specific account.
        """
        start_date = self._get_scraper_start_date(service, provider, account)
        creds = self.credentials_repo.get_credentials(service, provider, account)
        requires_2fa = is_2fa_required(service, provider)

        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            status = (
                history_repo.WAITING_FOR_2FA
                if requires_2fa
                else history_repo.IN_PROGRESS
            )
            process_id = history_repo.record_scrape_start(
                service, provider, account, start_date, status
            )

        scraper = get_scraper(service, provider, account, creds, start_date, process_id)
        thread = Thread(target=scraper.pull_data_to_db)
        thread.start()

        if requires_2fa:
            name = f"{service} - {provider} - {account}"
            _tfa_scrapers_waiting[name] = (scraper, thread)

        return process_id

    def submit_2fa_code(
        self, service: str, provider: str, account: str, code: str
    ) -> None:
        """Handle 2FA code submission."""
        name = f"{service} - {provider} - {account}"
        if name not in _tfa_scrapers_waiting:
            raise EntityNotFoundException("Scraping process not found")

        scraper, thread = _tfa_scrapers_waiting[name]
        scraper.set_otp_code(code)

    def abort_scraping_process(self, process_id: int) -> None:
        """Abort any scraping process by its ID."""
        # Check if it's a 2FA-waiting scraper
        target_name = None
        for name, (scraper, _) in _tfa_scrapers_waiting.items():
            if scraper.process_id == process_id:
                target_name = name
                break

        if target_name:
            # Cancel the 2FA scraper
            scraper, _ = _tfa_scrapers_waiting.pop(target_name)
            scraper.set_otp_code(scraper.CANCEL)

        # Mark as failed in the database regardless
        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(process_id, history_repo.FAILED)

    def _get_scraper_start_date(
        self, service: str, provider: str, account: str
    ) -> datetime.date:
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
            service, provider, account
        )
        if last_scrape:
            try:
                start_date = datetime.fromisoformat(last_scrape).date() - timedelta(
                    days=7
                )
            except:
                start_date = date.today() - timedelta(days=365)
        else:
            start_date = date.today() - timedelta(days=365)
        return start_date

    def _collect_scrapers(self, credentials: Dict) -> Tuple[Dict, Dict]:
        normal = {}
        tfa = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, acc_creds in accounts.items():
                    name = f"{service} - {provider} - {account}"
                    scraper = get_scraper(service, provider, account, acc_creds)
                    if scraper.requires_2fa:
                        tfa[name] = scraper
                    else:
                        normal[name] = scraper
        return normal, tfa
