from datetime import datetime, date
from threading import Thread
from time import sleep

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

        Parameters
        ----------
        scraper : Scraper
            The scraper to use for fetching the data
        start_date : date | str
            The date from which to start fetching the data

        Returns
        -------
        dict
            If 2FA is required, returns a dict with key 'waiting_for_2fa' and a dict containing the name, scraper, and thread.
            Otherwise, returns a dict with key 'status' and the status dictionary.
        """
        thread = Thread(target=scraper.pull_data_to_db, args=(start_date,))
        thread.start()
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"

        while thread.is_alive():
            if scraper.otp_code == "waiting for input":
                # Return status indicating 2FA is required, along with scraper and thread
                return {"waiting_for_2fa": {"name": name, "scraper": scraper, "thread": thread}}
            if scraper.otp_code == "not required":
                thread.join()
            sleep(1)  # Sleep to avoid busy waiting

        status = ScrapingRepository.get_scraper_status(scraper)
        return {"status": status}

    @staticmethod
    def handle_2fa_code(scraper, thread, code):
        """
        Handle the submission of a 2FA code to the scraper and wait for the thread to finish.

        Parameters
        ----------
        scraper : Scraper
            The scraper object waiting for 2FA.
        thread : Thread
            The thread running the scraping operation.
        code : str
            The 2FA code to submit (or 'cancel' to abort).
        Returns
        -------
        None
        """
        scraper.set_otp_code(code)
        thread.join()

    @staticmethod
    def get_scraper_status(scraper):
        """
        Create a result dictionary based on the scraper's state.

        Parameters
        ----------
        scraper : Scraper
            The scraper that has completed its operation

        Returns
        -------
        dict
            Dictionary with success and failure information
        """
        results = {"success": {}, "failed": {}}

        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"
        if not scraper.error:
            results["success"][name] = f"{name} - Data fetched successfully: {datetime.now()}"
            results.pop("failed", None)
        else:
            results["failed"][name] = f"{name} - Data fetching failed: {datetime.now()}. Error: {scraper.error}"
            results.pop("success", None)

        return results
