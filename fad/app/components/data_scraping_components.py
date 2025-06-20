import datetime as dt
import streamlit as st

from fad.app.services.data_scraping_service import ScrapingService
from fad.app.services.credentials_service import CredentialsService
from fad.app.services.tagging_service import AutomaticTaggerService
from fad.app.data_access import get_db_connection


class DataScrapingComponent:
    """
    Component for managing data scraping operations in the application.

    This class provides UI components and functionality for selecting data sources,
    setting date ranges, initiating data scraping, and handling two-factor authentication
    during the scraping process.

    Attributes
    ----------
    scraping_service : ScrapingService
        Service for handling data scraping operations.
    creds_service : CredentialsService
        Service for managing user credentials.
    auto_tagging_service : AutomaticTaggerService
        Service for automatically tagging transactions.
    start_date : datetime.date or None
        The start date from which to scrape data.
    selected_scrapers : list[str]
        List of selected data sources to scrape.
    """
    def __init__(self):
        """
        Initialize the DataScrapingComponent.

        Creates instances of required services and initializes state variables.
        """
        self.scraping_service = st.session_state.setdefault("scraping_service", ScrapingService(get_db_connection()))
        self.creds_service = CredentialsService()
        self.auto_tagging_service = AutomaticTaggerService(get_db_connection())
        self.start_date = None
        self.selected_scrapers = []

    def set_scraping_start_date(self) -> None:
        """
        Set the start date for scraping data.

        Creates a date input widget with a default value of two weeks before the latest
        data date. Validates that the selected date is not in the future.

        Returns
        -------
        None
            Updates the start_date attribute with the selected date.
        """
        latest_data_date = self.scraping_service.get_latest_data_date() - dt.timedelta(days=14)
        start_date = st.date_input("Set the date from which to start fetching your data "
                                   "(Defaults to 2 weeks previously to the latest date in your data).",
                                   value=latest_data_date)
        if start_date > dt.date.today():
            st.warning("You cannot set a start date in the future. Please select a valid date.")
            start_date = dt.date.today()

        self.start_date = start_date

    def select_services_to_scrape(self) -> None:
        """
        Select the services to scrape data from.

        Creates a multiselect widget populated with available data sources from the
        credentials service. Updates the selected_scrapers attribute with the user's selections.

        Returns
        -------
        None
            Updates the selected_scrapers attribute with the selected services.
        """
        available_service: list[str] = self.creds_service.get_available_data_sources()
        self.selected_scrapers = st.multiselect(
            "Select the services to scrape data from",
            options=available_service,
            default=available_service,
            key="selected_services"
        )

    def fetch_and_process_data(self) -> None:
        """
        Fetch and process financial data from selected services.

        Creates a button to initiate data scraping. When clicked, it clears previous
        scraping status, initiates data scraping from selected sources, and applies
        automatic tagging rules to the fetched data. Also handles two-factor authentication
        and displays scraping status messages.

        Returns
        -------
        None
            Initiates data scraping and displays results.
        """
        credentials: dict = self.creds_service.get_data_sources_credentials(self.selected_scrapers)
        if st.button("Fetch Data"):
            self.scraping_service.clear_scraping_status()
            self.scraping_service.clear_waiting_for_2fa_scrapers()
            self.scraping_service.pull_data_from_scrapers_to_db(self.start_date, credentials)
            self.auto_tagging_service.update_raw_data_by_rules()  # move this to within the service

        self.tfa_fragments()
        self.display_scraping_status()

    def tfa_fragments(self) -> None:
        """
        Create fragments for handling two-factor authentication (2FA) code input.

        Retrieves any scrapers waiting for 2FA from the session state and creates
        input dialogs for each one. This will be used to display the 2FA input dialog
        when needed during the scraping process.

        Returns
        -------
        None
            Creates UI components for 2FA input.
        """
        tfa_scrapers_waiting: dict = st.session_state.get("tfa_scrapers_waiting", {})
        for name, (scraper, thread) in tfa_scrapers_waiting.items():
            self.tfa_code_input(scraper, thread)

    @st.fragment
    def tfa_code_input(self, scraper: object, thread: object) -> None:
        """
        Display a dialog for the user to enter the OTP code for the given provider.

        Creates a UI container with input field and buttons for handling two-factor
        authentication. The dialog will stop the script until the user submits the code
        or cancels. If the user cancels the 2FA, the script will rerun. If the user
        submits a code, it will be passed to the scraper and the script will rerun.

        Parameters
        ----------
        scraper : object
            The scraper object for which to handle two-factor authentication.
            Contains service_name, provider_name, and account_name attributes.
        thread : object
            The thread object that is running the scraping operation.

        Returns
        -------
        None
            Updates the session state and triggers a rerun when appropriate.
        """
        with st.container(border=True):
            name = f"{scraper.service_name} - {scraper.provider_name} - {scraper.account_name}"
            st.subheader(name)

            code = st.text_input('Code', key=f'tfa_code_input_{name}', label_visibility="hidden",
                                 placeholder='Enter two factor authentication code here')
            col_1, col_2, _ = st.columns([1, 1, 8])
            if col_1.button('Submit', key=f"two_fa_dialog_submit_{name}"):
                self.scraping_service.scraping_repo.handle_2fa_code(scraper, thread, code)
                st.session_state["tfa_scrapers_waiting"].pop(name, None)  # remove the scraper from the waiting list`
                self.scraping_service.update_scrapers_status(scraper)
                self.auto_tagging_service.update_raw_data_by_rules()
                st.rerun()
            if col_2.button('Cancel', key=f"two_fa_dialog_cancel_{name}"):
                self.scraping_service.scraping_repo.handle_2fa_code(scraper, thread, "cancel")
                st.session_state["tfa_scrapers_waiting"].pop(name, None)  # remove the scraper from the waiting list
                st.rerun()

    def display_scraping_status(self) -> None:
        """
        Display success and error messages from data scraping.

        Iterates through the scraping status messages and displays them as
        appropriate UI notifications. Failed or waiting statuses are shown as
        warnings, while successful operations are shown as success messages.

        Returns
        -------
        None
            Displays status messages in the UI.
        """
        for type_, messages in self.scraping_service.scraping_status.items():
            if type_ in ['failed', 'waiting for 2fa']:
                for msg in messages.values():
                    st.warning(msg, icon="⚠️")
            else:
                for msg in messages.values():
                    st.success(msg, icon="✅")
