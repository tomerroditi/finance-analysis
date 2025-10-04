from datetime import datetime

# Removed: import streamlit as st
from streamlit.connections import SQLConnection

from fad import DB_PATH
from fad.app.data_access import get_db_connection
from fad.app.data_access.scraping_history_repository import ScrapingHistoryRepository
from fad.app.data_access.scraping_repository import ScrapingRepository
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.services.transactions_service import TransactionsService
from fad.scraper import Scraper, get_scraper


class ScrapingService:
    """
    Service for managing data scraping operations.

    This class provides methods for pulling data from various financial services,
    handling two-factor authentication, and managing scraping status. It interacts
    with the database through repository classes.

    Attributes
    ----------
    conn : object
        Database connection object.
    transactions_repo : TransactionsRepository
        Repository for transaction data operations.
    scraping_repo : ScrapingRepository
        Repository for scraping operations.
    scraping_history_repo : ScrapingHistoryRepository
        Repository for scraping history operations.
    scraping_status : dict
        Dictionary tracking the status of scraping operations.
    tfa_scrapers_waiting : dict
        Dictionary of scrapers currently waiting for 2FA input.
    """
    def __init__(self, conn: SQLConnection = get_db_connection()):
        """
        Initialize the ScrapingService.

        Parameters
        ----------
        conn : object
            Database connection object to use for database operations.
        """
        self.conn = conn
        self.transactions_repo = TransactionsRepository(conn)
        self.transactions_service = TransactionsService(conn)
        self.scraping_repo = ScrapingRepository()
        self.scraping_history_repo = ScrapingHistoryRepository(conn)
        self.scraping_status = {"success": {}, "failed": {}, "waiting_for_2fa": {}}
        self.tfa_scrapers_waiting = {}  # {name: (scraper, thread)}

    def get_latest_data_date(self):
        """
        Get the latest date of data in the database.

        Returns
        -------
        datetime.date
            The latest date for which data exists in the database.
        """
        return self.transactions_service.get_latest_data_date()

    def get_scraping_results(self):
        """
        Get the current scraping results.

        Returns
        -------
        dict
            Dictionary containing success and failure statuses of scraping operations.
        """
        return self.scraping_status

    def pull_data_from_scrapers_to_db(self, start_date, credentials):
        """
        Pull data from the provided data sources from the given date to present and save it to the database file.

        Parameters
        ----------
        start_date : datetime | str
            The date from which to start pulling the data
        credentials : dict
            The credential dictionary
        """
        filtered_credentials = self._filter_scrapable_accounts(credentials)

        if not filtered_credentials:
            return

        normal_scraper, tfa_scrapers = self._collect_scrapers(filtered_credentials)
        self._scrape_normal_scrapers(normal_scraper, start_date)
        self._scrape_tfa_scrapers(tfa_scrapers, start_date)

    def _filter_scrapable_accounts(self, credentials):
        """
        Filter credentials to only include accounts that can be scraped today.

        Parameters
        ----------
        credentials : dict
            Dictionary containing credentials for various services, providers, and accounts.

        Returns
        -------
        dict
            Filtered credentials dictionary containing only accounts that haven't been scraped today.
        """
        filtered_credentials = {}

        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, account_credentials in accounts.items():
                    # Check if this account can be scraped today
                    if self.scraping_history_repo.can_scrape_today(service, provider, account):
                        # Add to filtered credentials
                        if service not in filtered_credentials:
                            filtered_credentials[service] = {}
                        if provider not in filtered_credentials[service]:
                            filtered_credentials[service][provider] = {}
                        filtered_credentials[service][provider][account] = account_credentials
                    else:
                        # Add to status as already scraped today
                        account_key = f"{service} - {provider} - {account}"
                        self.scraping_status["failed"][account_key] = f"{account_key} - already scraped today"

        return filtered_credentials

    def get_accounts_scraped_today(self):
        """
        Get a summary of accounts that were scraped today.

        Returns
        -------
        dict
            Summary of today's scraping activity.
        """
        return self.scraping_history_repo.get_todays_scraping_summary()

    def get_max_failed_scraping_attempts(self):
        """
        Get the maximum number of allowed failed scraping attempts per account.

        Returns
        -------
        int
            Maximum number of allowed failed scraping attempts.
        """
        return self.scraping_history_repo.MAX_FAILED_ATTEMPTS_PER_DAY

    @staticmethod
    def _collect_scrapers(credentials):
        """
        Collect and categorize scrapers based on whether they require 2FA.

        Iterates through the credentials dictionary and creates appropriate scraper
        instances for each service, provider, and account combination. Separates
        scrapers into those that require two-factor authentication and those that don't.

        Parameters
        ----------
        credentials : dict
            Dictionary containing credentials for various services, providers, and accounts.

        Returns
        -------
        tuple
            A tuple containing two dictionaries:
            - normal_scrapers: Dictionary of scrapers that don't require 2FA
            - tfa_scrapers: Dictionary of scrapers that require 2FA
        """
        normal_scrapers = {}
        tfa_scrapers = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, credentials in accounts.items():
                    resource_name = f"{service} - {provider} - {account}"
                    scraper = get_scraper(service, provider, account, credentials)
                    if scraper.requires_2fa:
                        tfa_scrapers[resource_name] = scraper
                    else:
                        normal_scrapers[resource_name] = scraper
        return normal_scrapers, tfa_scrapers

    def _scrape_normal_scrapers(self, scrapers: dict, start_date):
        """
        Scrape data from normal scrapers (without 2FA) and save to the database.

        Parameters
        ----------
        scrapers : dict
            Dictionary of normal scrapers to scrape.
        start_date : datetime | str
            The date from which to start pulling the data.
        """
        for _, scraper in scrapers.items():
            scraper.pull_data_to_db(start_date)
            self.update_scrapers_status(scraper)

    def _scrape_tfa_scrapers(self, scrapers: dict, start_date):
        """
        Scrape data from scrapers that require 2FA and save to the database.

        Parameters
        ----------
        scrapers : dict
            Dictionary of scrapers that require 2FA.
        start_date : datetime | str
            The date from which to start pulling the data.
        """
        for _, scraper in scrapers.items():
            result = self.scraping_repo.pull_data_from_2fa_scraper_to_db(scraper, start_date)
            if "waiting_for_2fa" in result:
                info = result["waiting_for_2fa"]
                self.tfa_scrapers_waiting[info["name"]] = (info["scraper"], info["thread"])
                self.scraping_status["waiting_for_2fa"][info["name"]] = f"{info['name']} - waiting for 2fa input"
            elif "status" in result:
                status = result["status"]
                for status_type in status:
                    self.scraping_status[status_type].update(status[status_type])

    def update_scrapers_status(self, scraper: Scraper):
        """
        Update the status of a scraper after it has completed its operation.

        Parameters
        ----------
        scraper : Scraper
            The scraper that has completed its operation.
        """
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"
        for type_ in self.scraping_status:
            self.scraping_status[type_].pop(name, None)
        status = self.scraping_repo.get_scraper_status(scraper)
        for status_type in status:
            self.scraping_status[status_type].update(status[status_type])

    def clear_scraping_status(self):
        """
        Clear the current scraping status.

        Resets the scraping_status dictionary to empty success, failed, and waiting for 2fa categories.

        Returns
        -------
        None
        """
        self.scraping_status = {"success": {}, "failed": {}, "waiting_for_2fa": {}}

    def clear_waiting_for_2fa_scrapers(self):
        """
        Clear the list of scrapers waiting for 2FA input.

        Terminates any active threads of scrapers waiting for two-factor authentication
        and removes them from the waiting list.

        Returns
        -------
        None
        """
        for scraper_name, (scraper, thread) in self.tfa_scrapers_waiting.items():
            if thread.is_alive():
                self.scraping_repo.handle_2fa_code(scraper, thread, "cancel")
                thread.join()
        self.tfa_scrapers_waiting = {}

    def get_tfa_scrapers_waiting(self):
        """
        Get the dictionary of scrapers currently waiting for 2FA input.

        Returns
        -------
        dict
            Dictionary of scrapers waiting for 2FA input.
        """
        return self.tfa_scrapers_waiting

    def handle_2fa_code(self, scraper_name, code):
        """
        Handle the submission of a 2FA code for a waiting scraper.

        Parameters
        ----------
        scraper_name : str
            The name of the scraper waiting for 2FA.
        code : str
            The 2FA code to submit (or 'cancel' to abort).
        Returns
        -------
        None
        """
        if scraper_name not in self.tfa_scrapers_waiting:
            return
        scraper, thread = self.tfa_scrapers_waiting[scraper_name]
        self.scraping_repo.handle_2fa_code(scraper, thread, code)
        # After 2FA, update status and remove from waiting
        self.update_scrapers_status(scraper)
        del self.tfa_scrapers_waiting[scraper_name]

    def clear_scraper_status(self, scraper_name):
        """
        Clear the scraping status for a single scraper.

        Parameters
        ----------
        scraper_name : str
            The name of the scraper (service - provider - account).
        Returns
        -------
        None
        """
        for type_ in self.scraping_status:
            self.scraping_status[type_].pop(scraper_name, None)

    def clear_waiting_for_2fa_scraper(self, scraper_name):
        """
        Clear the waiting for 2FA state for a single scraper.

        Parameters
        ----------
        scraper_name : str
            The name of the scraper (service - provider - account).
        Returns
        -------
        None
        """
        if scraper_name in self.tfa_scrapers_waiting:
            scraper, thread = self.tfa_scrapers_waiting.pop(scraper_name)
            if thread.is_alive():
                self.scraping_repo.handle_2fa_code(scraper, thread, "cancel")
                thread.join()
