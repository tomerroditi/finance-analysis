import datetime as dt

import streamlit as st

from fad.app.services.credentials_service import CredentialsService
from fad.app.services.data_scraping_service import ScrapingService
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.app.naming_conventions import Services


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
        self.start_date = dt.date.today() - dt.timedelta(days=365)
        self.selected_scrapers = []

    def render_data_scraping(self):
        """
        Render the data scraping UI components.

        This method sets up the UI for selecting services to scrape data from and initiating the data fetching process.

        Returns
        -------
        None
        """
        self.display_scraping_summary()
        self.select_services_to_scrape()
        self.fetch_and_process_data()

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
        available_accounts = self.creds_service.get_available_data_sources()
        credit_cards_accounts = [account for account in available_accounts if account.lower().startswith(Services.CREDIT_CARD.value)]
        banks_accounts = [account for account in available_accounts if account.lower().startswith(Services.BANK.value)]

        if not credit_cards_accounts and not banks_accounts:
            st.page_link("fad/app/pages/my_accounts.py", label="No accounts found. Click here to add accounts.", icon="⚙️")
            return

        with st.container(border=True):
            selected_banks = st.pills(
                "Select banks to scrape data from",
                options=banks_accounts,
                default=banks_accounts,
                format_func=lambda account: account.split(" - ", 1)[-1],  # provider - account
                key="selected_banks",
                selection_mode="multi",
            )

            selected_credit_cards = st.pills(
                "Select credit cards to scrape data from",
                options=credit_cards_accounts,
                default=credit_cards_accounts,
                format_func=lambda account: account.split(" - ", 1)[-1],  # provider - account
                key="selected_credit_cards",
                selection_mode="multi",
            )

        self.selected_scrapers = selected_banks + selected_credit_cards

    def display_scraping_summary(self) -> None:
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

        if st.button("Scrape Data", key="scrape_data_main_button"):
            self.scraping_service.clear_scraping_status()
            self.scraping_service.clear_waiting_for_2fa_scrapers()
            start_dates = self.scraping_service.build_scraper_start_dates(credentials)
            self.scraping_service.pull_data_from_scrapers_to_db(start_dates, credentials)
            self._apply_tagging_rules()

            st.session_state["scraping_status"] = self.scraping_service.get_scraping_results()
            st.session_state["tfa_scrapers_waiting"] = self.scraping_service.get_tfa_scrapers_waiting()

        self.tfa_fragments()
        self.display_scraping_status()

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
        for name in tfa_scrapers_waiting.keys():
            self.tfa_code_input(name)

    @st.fragment
    def tfa_code_input(self, name: str) -> None:
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
                    self.scraping_service.clear_scraper_status(name)
                    self.scraping_service.clear_waiting_for_2fa_scraper(name)
                    start_date = self.scraping_service.build_scraper_start_dates(single_creds)
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
