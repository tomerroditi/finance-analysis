from datetime import datetime
from threading import Thread
from time import sleep

import streamlit as st

from fad.scraper import Scraper


class ScrapingRepository:
    """
    Repository for scraping data from financial services.
    Manages the actual data fetching operations and database interactions.
    """
    @staticmethod
    def pull_data_from_2fa_scraper_to_db(scraper, start_date, db_path):
        """
        Fetch the data from the scraper and save it to the database

        Parameters
        ----------
        scraper : Scraper
            The scraper to use for fetching the data
        start_date : datetime | str
            The date from which to start fetching the data
        db_path : str
            The path to the database file. If None the database file will be created in the folder of fad package
            with the name 'data.db'

        Returns
        -------
        dict
            Dictionary containing success/failure/waiting statuses for the scraper
        """
        thread = Thread(target=scraper.pull_data_to_db, args=(start_date, db_path))
        thread.start()
        name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"

        while thread.is_alive():
            if scraper.otp_code == "waiting for input":
                st.session_state.setdefault("tfa_scrapers_waiting", {})[name] = (scraper, thread)
                return {"waiting for 2fa": {name: f"{name} - waiting for 2fa input"}}
            if scraper.otp_code == "not required":
                thread.join()
            sleep(1)  # Sleep to avoid busy waiting

        status = ScrapingRepository.get_scraper_status(scraper)
        return status

    @staticmethod
    def handle_2fa_code(scraper, thread, code):
        if code is None or code == '':
            st.error('Please enter a valid code')
            st.stop()
        st.write("Code submitted. Fetching data, please wait...")
        scraper.set_otp_code(code)
        thread.join()

    @staticmethod
    def get_scraper_status(scraper):
        """
        Create a result dictionary based on the scraper's state

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
