from datetime import datetime, date
from threading import Thread
from time import sleep
from typing import Dict, Any, Optional

from fad.scraper import Scraper


class ScrapingRepository:
    """
    Repository for scraping data from financial services.
    Manages the actual data fetching operations and database interactions.
    """
    @staticmethod
    def pull_data_from_2fa_scraper_to_db(scraper: Scraper, start_date: date | str):
        """
        Fetch the data from the scraper and save it to the database.
        """
        thread = Thread(target=scraper.pull_data_to_db, args=(start_date,))
        thread.start()
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"

        # In a real async environment, we might not want to block like this,
        # but the old app used this sync-wait-for-tfa pattern.
        # We'll adapt it to return status immediately if 2FA is needed.
        while thread.is_alive():
            if scraper.otp_code == "waiting for input":
                return {"waiting_for_2fa": {"name": name, "scraper": scraper, "thread": thread}}
            if scraper.otp_code == "not required":
                # Wait a bit or return and let the service handle polling?
                # For now, we'll wait a limited time if not required yet.
                pass
            sleep(0.5)

        status = ScrapingRepository.get_scraper_status(scraper)
        return {"status": status}

    @staticmethod
    def handle_2fa_code(scraper: Scraper, thread: Thread, code: str):
        """Handle 2FA code submission."""
        scraper.set_otp_code(code)
        thread.join()

    @staticmethod
    def get_scraper_status(scraper: Scraper) -> Dict[str, Dict[str, str]]:
        """Create a result dictionary based on the scraper's state."""
        results = {"success": {}, "failed": {}}
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"
        if not scraper.error:
            results["success"][name] = f"{name} - Data fetched successfully: {datetime.now()}"
        else:
            results["failed"][name] = f"{name} - Data fetching failed: {datetime.now()}. Error: {scraper.error}"
        return results
