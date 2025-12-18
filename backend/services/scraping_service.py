from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from threading import Thread

from sqlalchemy.orm import Session

from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.scraping_repository import ScrapingRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.repositories.credentials_repository import CredentialsRepository
from fad.scraper import get_scraper, Scraper

# In-memory storage for active scraping session
# This is acceptable for a local single-user desktop app
_scraping_status = {"success": {}, "failed": {}, "waiting_for_2fa": {}}
_tfa_scrapers_waiting: Dict[str, Tuple[Scraper, Thread]] = {}


class ScrapingService:
    """
    Service for managing data scraping operations.
    Handles background threads and 2FA wait states.
    """

    def __init__(self, db: Session):
        self.db = db
        self.transactions_repo = TransactionsRepository(db)
        self.scraping_repo = ScrapingRepository()
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository()

    def get_scraping_results(self) -> Dict:
        """Get the current scraping results."""
        return _scraping_status

    def get_todays_summary(self) -> Dict:
        """Get summary of accounts scraped today from history."""
        return self.scraping_history_repo.get_todays_scraping_summary()

    def start_scraping(self, service_filter: Optional[str] = None) -> None:
        """
        Start the scraping process for all (or filtered) credentials.
        """
        # 1. Load credentials
        all_creds = self.credentials_repo.read_credentials_file()
        if not all_creds:
            return

        # 2. Filter by service if requested
        if service_filter:
            all_creds = {k: v for k, v in all_creds.items() if k == service_filter}

        # 3. Filter only those that can be scraped today
        scrapable_creds = self._filter_scrapable_accounts(all_creds)
        if not scrapable_creds:
            return

        # 4. Build start dates
        start_dates = self._build_scraper_start_dates(scrapable_creds)

        # 5. Collect scrapers
        normal_scrapers, tfa_scrapers = self._collect_scrapers(scrapable_creds)

        # 6. Kick off normal scrapers
        for name, scraper in normal_scrapers.items():
            key = (scraper.service_name, scraper.provider_name, scraper.account_name)
            scraper.pull_data_to_db(start_dates.get(key))
            self.update_scrapers_status(scraper)

        # 7. Kick off TFA scrapers
        for name, scraper in tfa_scrapers.items():
            key = (scraper.service_name, scraper.provider_name, scraper.account_name)
            result = self.scraping_repo.pull_data_from_2fa_scraper_to_db(scraper, start_dates.get(key))
            
            if "waiting_for_2fa" in result:
                info = result["waiting_for_2fa"]
                _tfa_scrapers_waiting[info["name"]] = (info["scraper"], info["thread"])
                _scraping_status["waiting_for_2fa"][info["name"]] = f"{info['name']} - waiting for 2fa input"
            elif "status" in result:
                status = result["status"]
                for s_type in status:
                    _scraping_status[s_type].update(status[s_type])

    def handle_2fa_code(self, scraper_name: str, code: str) -> None:
        """Handle 2FA code submission."""
        if scraper_name not in _tfa_scrapers_waiting:
            return
            
        scraper, thread = _tfa_scrapers_waiting.pop(scraper_name)
        _scraping_status["waiting_for_2fa"].pop(scraper_name, None)
        
        self.scraping_repo.handle_2fa_code(scraper, thread, code)
        self.update_scrapers_status(scraper)

    def update_scrapers_status(self, scraper: Scraper) -> None:
        """Update the status dict after a scraper completes."""
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"
        for type_ in _scraping_status:
            _scraping_status[type_].pop(name, None)
            
        status = self.scraping_repo.get_scraper_status(scraper)
        for s_type in status:
            _scraping_status[s_type].update(status[s_type])

    def _filter_scrapable_accounts(self, credentials: Dict) -> Dict:
        filtered = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, account_creds in accounts.items():
                    if self.scraping_history_repo.can_scrape_today(service, provider, account):
                        if service not in filtered: filtered[service] = {}
                        if provider not in filtered[service]: filtered[service][provider] = {}
                        filtered[service][provider][account] = account_creds
                    else:
                        name = f"{service} - {provider} - {account}"
                        _scraping_status["failed"][name] = f"{name} - already scraped today"
        return filtered

    def _build_scraper_start_dates(self, credentials: Dict) -> Dict:
        start_dates = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account in accounts:
                    last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(service, provider, account)
                    if last_scrape:
                        try:
                            start_date = datetime.fromisoformat(last_scrape).date() - timedelta(days=7)
                        except:
                            start_date = date.today() - timedelta(days=365)
                    else:
                        start_date = date.today() - timedelta(days=365)
                    start_dates[(service, provider, account)] = start_date
        return start_dates

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

    def clear_status(self) -> None:
        """Reset the scraping status."""
        global _scraping_status
        _scraping_status = {"success": {}, "failed": {}, "waiting_for_2fa": {}}
