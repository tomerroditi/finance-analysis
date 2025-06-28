from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.data_access.scraping_repository import ScrapingRepository
from fad import DB_PATH
import streamlit as st
from datetime import datetime
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.scraper import Scraper, get_scraper
from fad import DB_PATH


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
    scraping_status : dict
        Dictionary tracking the status of scraping operations.
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
        self.scraping_repo = ScrapingRepository()
        self.scraping_status = st.session_state.setdefault("scraping_status", {"success": {}, "failed": {}, "waiting for 2fa": {}})

    def get_latest_data_date(self):
        """
        Get the latest date of data in the database.

        Returns
        -------
        datetime.date
            The latest date for which data exists in the database.
        """
        return self.transactions_repo.get_latest_data_date()

    def get_scraping_results(self):
        """
        Get the current scraping results.

        Returns
        -------
        dict
            Dictionary containing success and failure statuses of scraping operations.
        """
        return self.scraping_status

    def pull_data_from_scrapers_to_db(self, start_date, credentials, db_path: str = DB_PATH):
        """
        Pull data from the provided data sources from the given date to present and save it to the database file.

        Parameters
        ----------
        start_date : datetime | str
            The date from which to start pulling the data
        credentials : dict
            The credential dictionary
        db_path : str
            The path to the database file. If None, the database file will be created in the folder of fad package
            with the name 'data.db'

        """
        normal_scraper, tfa_scrapers = self._collect_scrapers(credentials)
        self._scrape_normal_scrapers(normal_scraper, start_date, db_path)
        self._scrape_tfa_scrapers(tfa_scrapers, start_date, db_path)

    def _collect_scrapers(self, credentials):
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

    def _scrape_normal_scrapers(self, scrapers: dict, start_date, db_path):
        """
        Scrape data from normal scrapers (without 2FA) and save to the database.

        Parameters
        ----------
        scrapers : dict
            Dictionary of normal scrapers to scrape.
        start_date : datetime | str
            The date from which to start pulling the data.
        db_path : str
            The path to the database file.

        Returns
        -------
        dict
            Dictionary containing success and failure statuses.
        """
        for resource_name, scraper in scrapers.items():
            scraper.pull_data_to_db(start_date, db_path)
            self.update_scrapers_status(scraper)

    def _scrape_tfa_scrapers(self, scrapers: dict, start_date, db_path):
        """
        Scrape data from scrapers that require 2FA and save to the database.

        Parameters
        ----------
        scrapers : dict
            Dictionary of scrapers that require 2FA.
        start_date : datetime | str
            The date from which to start pulling the data.
        db_path : str
            The path to the database file.

        Returns
        -------
        dict
            Dictionary containing success and failure statuses.
        """
        for resource_name, scraper in scrapers.items():
            status = self.scraping_repo.pull_data_from_2fa_scraper_to_db(scraper, start_date, db_path)
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
        for type_, messages in self.scraping_status.items():
            messages.pop(name, None)

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
        self.scraping_status = {"success": {}, "failed": {}, "waiting for 2fa": {}}

    def clear_waiting_for_2fa_scrapers(self):
        """
        Clear the list of scrapers waiting for 2FA input.

        Terminates any active threads of scrapers waiting for two-factor authentication
        and removes them from the session state.

        Returns
        -------
        None
        """
        # terminate the threads of scrapers waiting for 2FA input
        for scraper_name, (scraper, thread) in st.session_state.get("tfa_scrapers_waiting", {}).items():
            if thread.is_alive():
                self.scraping_repo.handle_2fa_code(scraper, thread, "cancel")
                thread.join()

        st.session_state["tfa_scrapers_waiting"] = {}
