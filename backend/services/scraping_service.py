from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple
from threading import Thread

from sqlalchemy.orm import Session

from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.credentials_repository import CredentialsRepository
from backend.scraper import get_scraper, Scraper
from backend.errors import EntityNotFoundException
from backend.database import get_db_context


_tfa_scrapers_waiting: Dict[str, Tuple[Scraper, Thread]] = {}

class ScrapingService:
    """
    Service for managing data scraping operations.
    Handles background threads and 2FA wait states.
    """
    def __init__(self, db: Session):
        self.db = db
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository()

    def get_scraping_status(self, scraping_process_id: str) -> Dict:
        """Get the current scraping status."""
        return self.scraping_history_repo.get_scraping_status(scraping_process_id)
    
    def start_scraping(self, accounts: List[Dict]) -> None:
        """
        Start the scraping process for multiple accounts.
        """
        for account in accounts:
            self.start_scraping_single(account['service'], account['provider'], account['account'])

    def start_scraping_single(self, service: str, provider: str, account: str) -> int:
        """
        Start the scraping process for a specific account.
        """
        start_date = self._get_scraper_start_date(service, provider, account)
        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            process_id = history_repo.record_scrape_start(service, provider, account, start_date)
        
        creds = self.credentials_repo.get_credentials(service, provider, account)
        scraper = get_scraper(service, provider, account, creds, start_date, process_id)

        if scraper.requires_2fa:
            thread = Thread(target=self._run_2fa_scraping_process, args=(scraper,))
            thread.start()
            _tfa_scrapers_waiting[f"{service} - {provider} - {account}"] = (scraper, thread)
        else:
            thread = Thread(target=self._run_regular_scraping_process, args=(scraper,))
            thread.start()
        
        return process_id

    def _run_regular_scraping_process(self, scraper: Scraper) -> None:
        """
        Internal method to run the scraping logic.
        """
        scraper.pull_data_to_db()

    def _run_2fa_scraping_process(self, scraper: Scraper) -> None:
        """
        Internal method to run the 2FA scraping logic.
        """
        scraper.pull_data_to_db()

    def handle_2fa_code(self, service: str, provider: str, account: str, code: str) -> None:
        """Handle 2FA code submission."""
        name = f"{service} - {provider} - {account}"
        if name not in _tfa_scrapers_waiting:
            raise EntityNotFoundException("Scraping process not found")
        
        scraper, thread = _tfa_scrapers_waiting.pop(name)
        scraper.set_otp_code(code)

    def _get_scraper_start_date(self, service: str, provider: str, account: str) -> datetime.date:
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(service, provider, account)
        if last_scrape:
            try:
                start_date = datetime.fromisoformat(last_scrape).date() - timedelta(days=7)
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
