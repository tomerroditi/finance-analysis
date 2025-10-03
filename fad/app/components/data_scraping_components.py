import datetime as dt

import streamlit as st

from fad.app.services.credentials_service import CredentialsService
from fad.app.services.data_scraping_service import ScrapingService
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.scraper.scrapers import Scraper


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
    tagging_rules_service : TaggingRulesService
        Service for automatically applying tagging rules to transactions.
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
        if "scraping_service" not in st.session_state:
            st.session_state["scraping_service"] = ScrapingService()
        self.scraping_service = st.session_state["scraping_service"]
        self.creds_service = CredentialsService()
        self.tagging_rules_service = TaggingRulesService()
        self.start_date = None
        self.selected_scrapers = []

    def set_scraping_start_date(self) -> None:
        """
        Set the start date for scraping data.

        Creates a date input widget with a default value of one year ago. Validates
        the selected date to ensure it is not in the future. Updates the start_date
        attribute with the selected date.

        Returns
        -------
        None
            Updates the start_date attribute with the selected date.
        """
        start_date = st.date_input("Set the date from which to start fetching your data "
                                   "(Defaults to 1 year ago - which is the max range for most banks and credit cards)",
                                   value=dt.date.today() - dt.timedelta(days=365),)
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

        if st.button("Fetch Data", key="fetch_data_main_button"):
            self.scraping_service.clear_scraping_status()
            self.scraping_service.clear_waiting_for_2fa_scrapers()
            self.scraping_service.pull_data_from_scrapers_to_db(self.start_date, credentials)
            self._apply_tagging_rules()

            st.session_state["scraping_status"] = self.scraping_service.get_scraping_results()
            st.session_state["tfa_scrapers_waiting"] = self.scraping_service.get_tfa_scrapers_waiting()

        self._display_scraping_summary()
        self.tfa_fragments()
        self.display_scraping_status()

    def _display_scraping_summary(self) -> None:
        """
        Display a summary of today's scraping activity and account availability.

        Shows which accounts have already been scraped today and provides
        information about the daily scraping restriction policy.
        """
        summary = self.scraping_service.get_accounts_scraped_today()
        with st.expander(f"📊 Daily Scraping Summary - {len(summary["unavailable_to_scrape"])} account(s) already scraped today", expanded=False):
            st.info("**Accounts already scraped today (will be skipped)**")

            # Display each account in a more readable format
            if len(summary['succeed_today']) > 0:
                st.markdown("**Succeed to scrape today:**")
                for account in summary['succeed_today']:
                    st.write(f"• **{account}**")

            if len(summary['failed_today']) > 0:
                st.markdown(f"**Faild to scrape today (max {self.scraping_service.get_max_failed_scraping_attempts()} retries per account):**")
                for account, count in summary['failed_today'].items():
                    if account in summary["succeed_today"]:
                        continue  # Skip accounts that succeeded
                    st.write(f"• **{account}** (Failed attempts: {count})")

            if len(summary['canceled_today']) > 0:
                st.markdown("**Canceled attempts today (max 3 retries per account):**")
                for account, count in summary['canceled_today'].items():
                    if account in summary["succeed_today"]:
                        continue  # Skip accounts that succeeded
                    st.write(f"• **{account}** (Canceled attempts: {count})")

            st.markdown("---")
            st.markdown("""
            💡 **Daily Scraping Policy:**
            - Each account can only be successfully scraped once per day
            - Failed attempts can be retried up to 3 times per day
            - Canceled attempts (e.g., due to 2FA cancellation) can be retried up to 3 times per day
            - This helps comply with financial institutions' usage policies
            - Restrictions reset automatically at midnight
            """)

    def _apply_tagging_rules(self) -> None:
        """
        Apply tagging rules to all services after data scraping.
        This replaces the old AutomaticTaggerService functionality.
        """
        try:
            total_tagged = self.tagging_rules_service.apply_rules()
            if total_tagged > 0:
                st.success(f"Applied tagging rules! Tagged {total_tagged} transactions.")
        except Exception as e:
            st.warning(f"Failed to apply some tagging rules: {str(e)}")

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
            self.tfa_code_input(name, scraper, thread)

    @st.fragment
    def tfa_code_input(self, name: str, scraper: Scraper, thread: object) -> None:
        """
        Display a dialog for the user to enter the OTP code for the given provider.

        Creates a UI container with input field and buttons for handling two-factor
        authentication. The dialog will stop the script until the user submits the code
        or cancels. If the user cancels the 2FA, the script will rerun. If the user
        submits a code, it will be passed to the scraper and the script will rerun.
        Also provides a button to resend the code, which reruns the scraping command
        for the relevant scraper to trigger a new code to be sent.

        Parameters
        ----------
        name : str
            The name of the scraper (service - provider - account).
        scraper : Scraper
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
            st.subheader(name)
            code = st.text_input('Code', key=f'tfa_code_input_{name}', label_visibility="hidden",
                                 placeholder='Enter two factor authentication code here')
            col_1, col_2, col_3, _ = st.columns([1, 1, 1, 7])
            if col_1.button('Submit', key=f"two_fa_dialog_submit_{name}"):
                if not code:
                    st.error('Please enter a valid code')
                    st.stop()
                self.scraping_service.handle_2fa_code(name, code)
                self._apply_tagging_rules()

                st.session_state["scraping_status"] = self.scraping_service.get_scraping_results()
                st.session_state["tfa_scrapers_waiting"] = self.scraping_service.get_tfa_scrapers_waiting()
                st.rerun()
            if col_2.button('Cancel', key=f"two_fa_dialog_cancel_{name}"):
                self.scraping_service.handle_2fa_code(name, "cancel")
                st.session_state["scraping_status"] = self.scraping_service.get_scraping_results()
                st.session_state["tfa_scrapers_waiting"] = self.scraping_service.get_tfa_scrapers_waiting()
                st.rerun()
            if col_3.button('Resend Code', key=f"two_fa_dialog_resend_{name}"):
                # Resend code by rerunning the scraping command for this scraper only
                # Use get_scraper_credentials to fetch only the relevant credentials
                try:
                    service, provider, account = [x.strip() for x in name.split("-")]
                    single_creds = self.creds_service.get_scraper_credentials(service, provider, account)
                    start_date = self.start_date if self.start_date else dt.date.today()
                    self.scraping_service.clear_scraper_status(name)
                    self.scraping_service.clear_waiting_for_2fa_scraper(name)
                    self.scraping_service.pull_data_from_scrapers_to_db(start_date, single_creds)
                    st.session_state["scraping_status"] = self.scraping_service.get_scraping_results()
                    st.session_state["tfa_scrapers_waiting"] = self.scraping_service.get_tfa_scrapers_waiting()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not resend code: {e}")

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
        scraping_status = st.session_state.get("scraping_status", self.scraping_service.get_scraping_results())
        for type_, messages in scraping_status.items():
            if type_ in ['failed', 'waiting_for_2fa']:
                for msg in messages.values():
                    st.warning(msg, icon="⚠️")
            else:
                for msg in messages.values():
                    st.success(msg, icon="✅")
