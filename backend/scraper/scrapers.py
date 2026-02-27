import datetime
import os
import subprocess
from abc import ABC, abstractmethod
from threading import Event
from time import sleep

import pandas as pd

from backend.database import get_db_context
from backend.constants.tables import (
    BankTableFields,
    CreditCardTableFields,
    Tables,
    TransactionsTableFields,
)
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.scraper import NODE_JS_SCRIPTS_DIR
from backend.scraper.exceptions import (
    AccountError,
    ConnectionError,
    CredentialsError,
    DataError,
    ErrorType,
    LoginError,
    PasswordChangeError,
    RateLimitError,
    ScraperError,
    SecurityError,
    ServiceError,
    TimeoutError,
    TwoFactorRequiredError,
)
from backend.services.bank_balance_service import BankBalanceService
from backend.services.tagging_rules_service import TaggingRulesService
from backend.services.tagging_service import CategoriesTagsService


def get_scraper(
    service_name: str,
    provider_name: str,
    account_name: str,
    credentials: dict,
    start_date: datetime,
    process_id: int,
):
    """Return the appropriate Scraper subclass for the given service and provider.

    In demo mode, all real providers are transparently redirected to test
    scrapers so that scraping works without real credentials.

    Parameters
    ----------
    service_name : str
        Service type: ``credit_cards``, ``banks``, or ``insurance``.
    provider_name : str
        Provider identifier (e.g. ``isracard``, ``hapoalim``, ``max``).
    account_name : str
        User-assigned account label; allows multiple accounts per provider.
    credentials : dict
        Login fields for the provider (keys vary per provider).
    start_date : datetime.date
        Oldest transaction date to fetch.
    process_id : int
        Scraping history record ID for status tracking.

    Returns
    -------
    Scraper
        Concrete scraper instance ready to call ``pull_data_to_db``.

    Raises
    ------
    ValueError
        If ``service_name`` is not supported.
    """
    from backend.config import AppConfig

    # In demo mode, redirect real providers to test scrapers
    if AppConfig().is_demo_mode and "test_" not in provider_name:
        if service_name == "credit_cards":
            return DummyCreditCardScraper(
                account_name, credentials, start_date, process_id
            )
        elif service_name == "banks":
            return DummyRegularScraper(
                account_name, credentials, start_date, process_id
            )

    if service_name == "credit_cards":
        if provider_name == "isracard":
            return IsracardScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "max":
            return MaxScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "visa cal":
            return VisaCalScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "amex":
            return AmexScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "beyahad bishvilha":
            return BeyahadBishvilhaScraper(
                account_name, credentials, start_date, process_id
            )
        elif provider_name == "behatsdaa":
            return BehatsdaaScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "test_credit_card":
            return DummyCreditCardScraper(
                account_name, credentials, start_date, process_id
            )
        elif provider_name == "test_credit_card_2fa":
            return DummyCreditCardTFAScraper(
                account_name, credentials, start_date, process_id
            )
    elif service_name == "banks":
        if provider_name == "onezero":
            return OneZeroScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "hapoalim":
            return HapoalimScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "leumi":
            return LeumiScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "discount":
            return DiscountScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "mizrahi":
            return MizrahiScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "mercantile":
            return MercantileScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "otsar hahayal":
            return OtsarHahayalScraper(
                account_name, credentials, start_date, process_id
            )
        elif provider_name == "union":
            return UnionScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "beinleumi":
            return BeinleumiScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "massad":
            return MassadScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "yahav":
            return YahavScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "test_bank":
            return DummyRegularScraper(
                account_name, credentials, start_date, process_id
            )
        elif provider_name == "test_bank_2fa":
            return DummyTFAScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "dummy_tfa":
            return DummyTFAScraper(account_name, credentials, start_date, process_id)
        elif provider_name == "dummy_tfa_no_otp":
            return DummyTFAScraperNoOTP(
                account_name, credentials, start_date, process_id
            )
        elif provider_name == "dummy_regular":
            return DummyRegularScraper(
                account_name, credentials, start_date, process_id
            )
    elif service_name == "insurance":
        return InsuranceScraper(account_name, credentials, start_date, process_id)
    else:
        raise ValueError(f"The service name {service_name} is not supported yet.")


def is_2fa_required(service_name: str, provider_name: str):
    """
    Check if the scraper requires 2FA (Two-Factor Authentication)

    Parameters
    ----------
    service_name : str
        The name of the service of the scraper. banks, credit_cards, insurance, etc.
    provider_name : str
        The name of the provider of the scraper. isracard, hapoalim, max, etc.

    Returns
    -------
    bool
        True if the scraper requires 2FA, False otherwise
    """
    needs_2fa_map = {
        "banks": ["onezero", "test_bank_2fa"],
        "credit_cards": ["test_credit_card_2fa"],
    }
    return (
        service_name in needs_2fa_map and provider_name in needs_2fa_map[service_name]
    )


class Scraper(ABC):
    """
    An abstract class to scrape data from different providers and save them to the database using Node.js scripts and
    pandas DataFrames.

    This class should be inherited by the specific scraper classes.

    Attributes
    ----------
    account_name : str
        The name of the account to use to log data into the database
    credentials : dict
        A dictionary containing the credentials to log in to the websites
    result : str
        The result of the scraping process
    error : str
        The error message if an error occurs during the scraping process
    data : pd.DataFrame
        The scraped data as a pandas DataFrame. empty DataFrame is returned if no data was found
    otp_code : str
        The OTP (One-Time Password) code to be used for the 2FA process. entering "cancel" will cancel the scraping
        process.
    otp_event : Event
        An event to notify when the OTP code is available
    history_repo : ScrapingHistoryRepository
        A repository to record the scraping history
    requires_2fa : bool
        A flag to indicate if the scraper requires 2FA (Two-Factor Authentication)
    CANCEL : str
        A constant to indicate that the scraping process was canceled
    """

    requires_2fa = False
    CANCEL = "cancel"

    def __init__(
        self,
        account_name: str,
        credentials: dict,
        start_date: datetime.date,
        process_id: int,
    ):
        """Initialise the scraper with account details and session metadata.

        Parameters
        ----------
        account_name : str
            User-assigned label for the account; used to identify rows in the DB.
        credentials : dict
            Provider login fields (keys vary by provider, e.g. ``username``,
            ``password``, ``id``, ``phoneNumber``). Passwords are retrieved from
            the OS Keyring by the service layer before being passed here.
        start_date : datetime.date
            Oldest transaction date to fetch from the provider.
        process_id : int
            Scraping history record ID used to update the status on completion.
        """
        self.account_name = account_name
        self.credentials = credentials
        self.process_id = process_id
        self.start_date = start_date
        self.result = ""
        self.error = ""
        self.error_type = None
        self.data = None

        # 2fa related attributes
        self.otp_code = None
        self.otp_event = Event()

    @property
    def is_waiting_for_otp(self) -> bool:
        """Check if the scraper is currently waiting for an OTP code."""
        return self.otp_code == "waiting for input"

    @property
    @abstractmethod
    def service_name(self) -> str:
        """
        The name of the service
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        The name of the provider
        """
        pass

    @property
    @abstractmethod
    def script_path(self) -> dict:
        """
        A dictionary containing the paths to the Node.js scripts for each provider
        """
        pass

    @property
    @abstractmethod
    def table_name(self) -> str:
        """
        The name of the table to save the data to
        """
        pass

    @property
    @abstractmethod
    def table_unique_key(self) -> str:
        """
        The unique key in the table which is used to identify duplicated rows
        """
        pass

    @property
    @abstractmethod
    def sort_by_columns(self) -> list[str]:
        """
        The columns to sort the data by
        """
        pass

    def pull_data_to_db(self):
        """Scrape transactions and persist them to the database.

        Calls ``scrape_data``, enriches the DataFrame with account/provider
        columns, saves to the appropriate table, applies auto-tagging rules,
        and (for bank scrapers) recalculates bank balances. Records the outcome
        in the scraping history table regardless of success or failure.
        """
        print(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.provider_name}: {self.account_name}: Scraping data from {self.provider_name} ({self.start_date}) started",
            flush=True,
        )
        try:
            self.scrape_data(self.start_date.strftime("%Y-%m-%d"))
            if not self.data.empty:
                self.data = self.data.sort_values(by=self.sort_by_columns)
                self.data = self._add_account_name_and_provider_columns(self.data)
                self.data = self._add_missing_columns(self.data)
                self._save_scraped_transactions()
                self._apply_auto_tagging()
                self._recalculate_bank_balances()
        except CredentialsError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(f"DEBUG: Credentials error details: {e.original_error}", flush=True)
            return
        except ConnectionError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(f"DEBUG: Connection error details: {e.original_error}", flush=True)
            return
        except TimeoutError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(f"DEBUG: Timeout error details: {e.original_error}", flush=True)
            return
        except DataError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(f"DEBUG: Data error details: {e.original_error}", flush=True)
            return
        except TwoFactorRequiredError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(
                f"DEBUG: 2FA required error details: {e.original_error}", flush=True
            )
            return
        except LoginError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(f"DEBUG: Login error details: {e.original_error}", flush=True)
            return
        except ScraperError as e:
            print(
                f"{self.provider_name}: {self.account_name}: {self.error}", flush=True
            )
            print(
                f"DEBUG: General scraper error details: {e.original_error}", flush=True
            )
            return
        except Exception as e:
            # Catch any other unexpected exceptions
            error_msg = (
                f"Unexpected error while scraping {self.provider_name}: {str(e)}"
            )
            print(f"{self.provider_name}: {self.account_name}: {error_msg}", flush=True)
            print(f"DEBUG: Unexpected error details: {str(e)}", flush=True)
            self.error = error_msg
            self.error_type = ErrorType.GENERAL.value
            return
        finally:
            self._record_scraping_attempt(self.process_id)

        print(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.provider_name}: {self.account_name}: Scraping data from {self.provider_name} ({self.start_date}) finished",
            flush=True,
        )

        if self.data.empty:
            if self.otp_code == self.CANCEL:
                print(
                    f"{self.provider_name}: {self.account_name}: The scraping process was canceled"
                )
            else:
                print(
                    f"{self.provider_name}: {self.account_name}: No transactions found"
                )
            return

    @abstractmethod
    def scrape_data(self, start_date: str) -> pd.DataFrame:
        """
        Get the data from the specified provider

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        pass

    def _scrape_data(self, start_date: str, *args) -> pd.DataFrame:
        """
        Get the data from the specified provider

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        args : tuple
            Additional arguments to pass to the scraping script
        """
        args = ["node", self.script_path, *args, start_date]
        timeout = 300  # seconds
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            self.result = ""
            error_msg = f"Timeout: The scraping process for {self.provider_name} - {self.account_name} took too long ({timeout} seconds) and was terminated"
            self.error = error_msg
            raise TimeoutError(error_msg, str(e))

        self.result = result.stdout
        self._handle_error(result.stderr)

        data = self._scraped_data_to_df(self.result)
        return data

    @staticmethod
    def _scraped_data_to_df(data: str) -> pd.DataFrame:
        """
        Convert the scraped data to a pandas DataFrame

        Parameters
        ----------
        data: str
            the scraped data in string format, should have the following format:
            'found N transactions for account number <account_number>\n'
            'key1: value1| key2: value2| ...| keyN: valueN\n'
            'key1: value1| key2: value2| ...| keyN: valueN\n'
            ...

            in case where no transactions were found, the data should be in the following format:
            'found 0 transactions for account number <account_number>\n'

        Returns
        -------
        pd.DataFrame
            the scraped data as a pandas DataFrame where the keys are the columns and the values are the rows. if no data
            was found, an empty DataFrame is returned

        """
        assert isinstance(data, str), "data should be a string"

        data = data.split("\n")
        data = [line for line in data if line.startswith("account number:")]
        if not data:
            return pd.DataFrame()
        data = [line.split("| ") for line in data]
        col_names = [item.split(": ")[0].replace(" ", "_") for item in data[0]]
        data = [[item.split(": ")[1] for item in line] for line in data]
        df = pd.DataFrame(data, columns=col_names)

        amount_col = TransactionsTableFields.AMOUNT.value
        date_col = TransactionsTableFields.DATE.value
        if amount_col in df.columns:  # convert to float
            df[amount_col] = df[amount_col].astype(float)
        if date_col in df.columns:  # convert to string of format 'YYYY-MM-DD'
            try:
                df[date_col] = df[date_col].apply(
                    lambda x: datetime.datetime.strptime(
                        x, "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).strftime("%Y-%m-%d")
                )
            except ValueError:
                df[date_col] = df[date_col].apply(
                    lambda x: datetime.datetime.strptime(x, "%Y-%m-%d").strftime(
                        "%Y-%m-%d"
                    )
                )
        return df

    def _add_account_name_and_provider_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add the account name and provider columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the account name and provider columns to

        Returns
        -------
        pd.DataFrame
            The DataFrame with the account name and provider columns added
        """
        match self.table_name:
            case Tables.CREDIT_CARD.value:
                account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
                provider_col = CreditCardTableFields.PROVIDER.value
            case Tables.BANK.value:
                account_name_col = BankTableFields.ACCOUNT_NAME.value
                provider_col = BankTableFields.PROVIDER.value
            case _:
                raise ValueError(
                    f"The table name {self.table_name} is not supported yet."
                )
        df[account_name_col] = self.account_name
        df[provider_col] = self.provider_name
        return df

    @abstractmethod
    def _add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add missing columns to the DataFrame to align all the scrapers

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the missing columns to
        """
        pass

    def _handle_error(self, error: str):
        """
        Handle the error message from the scraping script. This is the most generic way to handle errors, each scraper
        should implement its own error handling method since the error messages can be different for each provider.

        Parameters
        ----------
        error: str
            The error message from the scraping script

        Raises
        ------
        ScraperError
            Base exception for all scraper errors
        LoginError
            If a login error occurs during the scraping process
        CredentialsError
            If there's an issue with the credentials
        ConnectionError
            If there's a connection issue
        TimeoutError
            If a scraping operation times out
        DataError
            If there's an issue with the scraped data
        AccountError
            If there's an issue with the account (blocked, suspended, etc.)
        ServiceError
            If the service is unavailable (maintenance, etc.)
        RateLimitError
            If the scraper hits a rate limit or too many requests
        SecurityError
            If there's a security-related issue (CAPTCHA, additional verification, etc.)
        PasswordChangeError
            If a password change is required
        """
        # Store the original error for internal logging
        original_error = error

        # Extract the actual error message
        # Prevent taking warnings prints as errors, it is assumed that the actual login error starts with
        # "logging error: " since we attach it to the error in the js script
        error_parts = error.split("logging error: ")
        error = error_parts[-1] if len(error_parts) > 1 else ""

        if not error:
            return  # No error to handle

        # Log the original error for debugging purposes
        print(
            f"DEBUG: {self.provider_name}: {self.account_name}: Original error: {original_error}",
            flush=True,
        )

        # Map of error types to exception classes and user-friendly message templates
        error_handlers = {
            ErrorType.CREDENTIALS: (
                CredentialsError,
                "Invalid credentials. Please check your login details.",
            ),
            ErrorType.CONNECTION: (
                ConnectionError,
                "Connection error. Check your internet connection.",
            ),
            ErrorType.TIMEOUT: (
                TimeoutError,
                "Request timed out. Please try again.",
            ),
            ErrorType.DATA: (
                DataError,
                "Error processing data from provider.",
            ),
            ErrorType.LOGIN: (
                LoginError,
                "Login failed. Please check your credentials.",
            ),
            ErrorType.PASSWORD_CHANGE: (
                PasswordChangeError,
                "Password expired. Please update your password.",
            ),
            ErrorType.ACCOUNT: (
                AccountError,
                "Account issue. May be blocked or suspended.",
            ),
            ErrorType.SERVICE: (
                ServiceError,
                "Service unavailable. Try again later.",
            ),
            ErrorType.RATE_LIMIT: (
                RateLimitError,
                "Too many requests. Please wait and try again.",
            ),
            ErrorType.SECURITY: (
                SecurityError,
                "Security verification required.",
            ),
            ErrorType.TWO_FACTOR_REQUIRED: (
                TwoFactorRequiredError,
                "Two-factor authentication required. Please try again — you will be prompted to enter a verification code.",
            ),
            ErrorType.GENERAL: (
                ScraperError,
                f"Unexpected error: {error[:50]}..."
                if len(error) > 50
                else f"Error: {error}",
            ),
        }

        # Ensure error is a string
        if not isinstance(error, str):
            error = str(error)

        # Check for error prefixes from Node.js scripts
        for et in ErrorType:
            et_value = et.value
            if not isinstance(et_value, str):
                et_value = str(et_value)
            if error.startswith(et_value):
                error_type = et
                break
        else:
            error_type = (
                ErrorType.GENERAL
            )  # If no specific error type is found, default to GENERAL

        # Get the appropriate exception class and user message
        exception_class, user_message = error_handlers[error_type]

        # Store the user-friendly error message and error type
        self.error = user_message
        self.error_type = error_type.value

        # Raise the appropriate exception
        if error:
            raise exception_class(user_message, original_error)

    def set_otp_code(self, otp_code):
        """
        Set the OTP code to be used for the 2FA process. is used only by scrapers that require 2FA. calling this method
        will notify the scraper that the OTP code is available and will continue the scraping process.

        Parameters
        ----------
        otp_code : str
            The OTP (One-Time Password) code to be used for the 2FA process. entering "cancel" will cancel the scraping
            process.

        Returns
        -------
        None
        """
        self.otp_code = otp_code
        self.otp_event.set()  # Notify that the OTP code is available

    def _record_scraping_attempt(self, id_: int):
        """Update the scraping history record with the final status.

        Parameters
        ----------
        id_ : int
            Scraping history record ID (same as ``process_id`` passed at init).
        """
        # Determine the status based on whether we have data and no errors
        if (
            self.otp_code == self.CANCEL
        ):  # 2fa canceled by the user (self.data is an empty df)
            status = ScrapingHistoryRepository.CANCELED
            error_message = None
            error_type = None
        elif self.data is not None and not self.error:
            status = ScrapingHistoryRepository.SUCCESS
            error_message = None
            error_type = None
        else:
            status = ScrapingHistoryRepository.FAILED
            error_message = self.error
            error_type = self.error_type

        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(id_, status, error_message, error_type)

    def _save_scraped_transactions(self):
        """
        Save the scraped transactions to the database.
        Uses a fresh database session for clean session management.
        """
        with get_db_context() as db:
            transactions_repo = TransactionsRepository(db)
            transactions_repo.add_scraped_transactions(self.data, self.table_name)

    def _apply_auto_tagging(self):
        """
        Apply tagging rules to the newly scraped transactions.
        Only tags transactions that don't have a category (overwrite=False).
        """
        try:
            with get_db_context() as db:
                cat_and_tags_service = CategoriesTagsService(db)
                cat_and_tags_service.add_new_credit_card_tags()  # runs on all cc data so not most efficient
                tagging_rules_service = TaggingRulesService(db)
                count = tagging_rules_service.apply_rules(overwrite=False)
                count += tagging_rules_service.auto_tag_credit_cards_bills()
                if count > 0:
                    print(
                        f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.provider_name}: {self.account_name}: Auto-tagged {count} transactions",
                        flush=True,
                    )
        except Exception as e:
            print(
                f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.provider_name}: {self.account_name}: Error auto-tagging: {str(e)}",
                flush=True,
            )

    def _recalculate_bank_balances(self):
        """
        Recalculate bank balance after a successful scrape.
        Only runs for bank scrapers (service_name == 'banks').
        """
        if self.service_name != "banks":
            return
        try:
            with get_db_context() as db:
                balance_service = BankBalanceService(db)
                balance_service.recalculate_for_account(
                    self.provider_name, self.account_name
                )
        except Exception as e:
            print(
                f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{self.provider_name}: {self.account_name}: "
                f"Error recalculating bank balance: {str(e)}",
                flush=True,
            )


############################################
# Credit Card Scrapers
############################################
class CreditCardScraper(Scraper, ABC):
    """Abstract base class for all credit card provider scrapers.

    Subclasses must implement ``script_path`` and ``scrape_data``.
    Writes to the ``credit_card_transactions`` table.
    """

    service_name = "credit_cards"
    table_name = "credit_card_transactions"
    table_unique_key = "id"
    sort_by_columns = ["date"]

    @property
    @abstractmethod
    def script_path(self) -> dict:
        """
        A dictionary containing the paths to the Node.js scripts for each provider
        """
        pass

    def _add_account_name_and_provider_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add the account name and provider columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the account name and provider columns to

        Returns
        -------
        pd.DataFrame
            The DataFrame with the account name and provider columns added
        """
        account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
        provider_col = CreditCardTableFields.PROVIDER.value

        df[account_name_col] = self.account_name
        df[provider_col] = self.provider_name
        return df

    def _add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add missing columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the missing columns to
        """
        cols_to_add = [
            CreditCardTableFields.STATUS.value,
            CreditCardTableFields.CATEGORY.value,
            CreditCardTableFields.TAG.value,
        ]

        for col in cols_to_add:
            if col not in df.columns:
                df[col] = None
        return df


class IsracardScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "credit_cards", "isracard.js")
    provider_name = "isracard"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Isracard website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["id"],
            self.credentials["card6Digits"],
            self.credentials["password"],
        )
        self.data = self._scrape_data(start_date, *args)


class MaxScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "credit_cards", "max.js")
    provider_name = "max"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Max website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class VisaCalScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "credit_cards", "visa_cal.js")
    provider_name = "visa cal"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Visa CAL website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class AmexScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "credit_cards", "amex.js")
    provider_name = "amex"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the American Express website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["id"],
            self.credentials["card6Digits"],
            self.credentials["password"],
        )
        self.data = self._scrape_data(start_date, *args)


class BeyahadBishvilhaScraper(CreditCardScraper):
    script_path = os.path.join(
        NODE_JS_SCRIPTS_DIR, "credit_cards", "beyahad_bishvilha.js"
    )
    provider_name = "beyahad bishvilha"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Beyahad Bishvilha website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["id"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class BehatsdaaScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "credit_cards", "behatsdaa.js")
    provider_name = "behatsdaa"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Behatsdaa website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["id"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class DummyCreditCardScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "dummy_regular.js")
    provider_name = "test_credit_card"
    requires_2fa = False

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Dummy Regular scraper for Credit Cards
        """
        args = ()
        self.data = self._scrape_data(start_date, *args)


class DummyCreditCardTFAScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "dummy_tfa.js")
    provider_name = "test_credit_card_2fa"
    requires_2fa = True

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Dummy TFA scraper for Credit Cards
        """
        args = (
            self.credentials.get("email", "dummy@example.com"),
            self.credentials.get("password", "dummypass"),
            self.credentials.get("phoneNumber", "1234567890"),
            self.credentials.get("otpLongTermToken", "none"),
        )
        self.data = self._scrape_data(start_date, *args)

    def _scrape_data(self, start_date: str, *args) -> pd.DataFrame:
        """
        Get the data from the website (Interactive 2FA version)
        """
        args = ["node", self.script_path, *args, start_date]
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        # wait for the OTP code to be requested, and then send it
        start_time = datetime.datetime.now()
        max_wait_time = 300  # Maximum time to wait for OTP prompt or data in seconds

        while True:
            # Check if we've been waiting too long
            if (datetime.datetime.now() - start_time).total_seconds() > max_wait_time:
                print(
                    f"DEBUG: {self.provider_name}: Timed out waiting for OTP prompt or data output",
                    flush=True,
                )
                process.kill()
                break

            output = process.stdout.readline()
            if output:
                if "Enter OTP code:" in output:
                    self.otp_code = "waiting for input"
                    if not self.otp_event.wait(timeout=max_wait_time):
                        raise LoginError("Timeout: OTP code was not provided for 2FA")
                    if self.otp_code == self.CANCEL:
                        process.kill()
                        return pd.DataFrame()
                    process.stdin.write(self.otp_code + "\n")
                    process.stdin.flush()
                    process.stdin.close()
                    break
                elif (
                    "writing scraped data to console" in output
                ):  # long term token is valid
                    self.otp_code = "not required"
                    break
                elif (
                    "long term token is valid" in output
                ):  # Another indicator that 2FA is not needed
                    self.otp_code = "not required"
                    break
            sleep(0.3)

        while process.poll() is None:
            self.result += process.stdout.readline()

        self._handle_error(process.stderr.read())

        lines = self.result.split("\n")
        for line in lines:
            if "renewed long term token" in line:
                self.credentials["otpLongTermToken"] = line.split(":", 1)[-1].strip()
                with get_db_context() as db:
                    creds_repo = CredentialsRepository(db)
                    creds_repo.save_credentials(
                        self.service_name,
                        self.provider_name,
                        self.account_name,
                        self.credentials,
                    )
                break
            elif "long term token is valid" in line:
                break

        return self._scraped_data_to_df(self.result)


############################################
# Bank Scrapers
############################################
class BankScraper(Scraper, ABC):
    """Abstract base class for all bank provider scrapers.

    Subclasses must implement ``script_path`` and ``scrape_data``.
    Writes to the ``bank_transactions`` table and triggers bank balance
    recalculation after each successful scrape.
    """

    service_name = "banks"
    table_name = "bank_transactions"
    table_unique_key = "id"
    sort_by_columns = ["date"]

    @property
    @abstractmethod
    def script_path(self) -> dict:
        """
        A dictionary containing the paths to the Node.js scripts for each provider
        """
        pass

    def _add_account_name_and_provider_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add the account name and provider columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the account name and provider columns to

        Returns
        -------
        pd.DataFrame
            The DataFrame with the account name and provider columns added
        """
        account_name_col = BankTableFields.ACCOUNT_NAME.value
        provider_col = BankTableFields.PROVIDER.value

        df[account_name_col] = self.account_name
        df[provider_col] = self.provider_name
        return df

    def _add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add missing columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the missing columns to
        """
        cols_to_add = [
            BankTableFields.STATUS.value,
            BankTableFields.CATEGORY.value,
            BankTableFields.TAG.value,
        ]

        for col in cols_to_add:
            if col not in df.columns:
                df[col] = None
        return df


class OneZeroScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "onezero.js")
    provider_name = "onezero"
    requires_2fa = True

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the OneZero website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["email"],
            self.credentials["password"],
            self.credentials["phoneNumber"],
            self.credentials.get("otpLongTermToken", "none"),
        )
        self.data = self._scrape_data(start_date, *args)

    def _scrape_data(self, start_date: str, *args) -> pd.DataFrame:
        """
        Get the data from the Isracard website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        email : str
            The email to log in to the website
        password : str
            The password to log in to the website
        phoneNumber : str
            The phone number to log in to the website
        otpLongTermToken : str
            The OTP long-term token to log in to the website

        Returns
        -------
        pd.DataFrame
            The scraped data as a pandas DataFrame. empty DataFrame is returned if no data was found
        """
        args = ["node", self.script_path, *args, start_date]
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        # wait for the OTP code to be requested, and then send it
        start_time = datetime.datetime.now()
        max_wait_time = 300  # Maximum time to wait for OTP prompt or data in seconds

        while True:
            # Check if we've been waiting too long
            if (datetime.datetime.now() - start_time).total_seconds() > max_wait_time:
                print(
                    f"DEBUG: {self.provider_name}: Timed out waiting for OTP prompt or data output",
                    flush=True,
                )
                process.kill()
                break

            output = process.stdout.readline()
            if output:
                if "Enter OTP code:" in output:
                    self.otp_code = "waiting for input"
                    if not self.otp_event.wait(timeout=max_wait_time):
                        raise LoginError("Timeout: OTP code was not provided for 2FA")
                    if self.otp_code == self.CANCEL:
                        process.kill()
                        return pd.DataFrame()
                    process.stdin.write(self.otp_code + "\n")
                    process.stdin.flush()
                    process.stdin.close()
                    break
                elif (
                    "writing scraped data to console" in output
                ):  # long term token is valid
                    self.otp_code = "not required"
                    break
                elif (
                    "long term token is valid" in output
                ):  # Another indicator that 2FA is not needed
                    self.otp_code = "not required"
                    break
            sleep(0.3)

        while process.poll() is None:
            self.result += process.stdout.readline()

        self._handle_error(process.stderr.read())

        lines = self.result.split("\n")
        for line in lines:
            if "renewed long term token" in line:
                self.credentials["otpLongTermToken"] = line.split(":", 1)[-1].strip()
                with get_db_context() as db:
                    creds_repo = CredentialsRepository(db)
                    creds_repo.save_credentials(
                        self.service_name,
                        self.provider_name,
                        self.account_name,
                        self.credentials,
                    )
                break
            elif "long term token is valid" in line:
                break

        return self._scraped_data_to_df(self.result)


class DummyTFAScraper(OneZeroScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "dummy_tfa.js")
    provider_name = "dummy_tfa"
    requires_2fa = True

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Dummy TFA scraper

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials.get("email", "dummy@example.com"),
            self.credentials.get("password", "dummypass"),
            self.credentials.get("phoneNumber", "1234567890"),
            self.credentials.get("otpLongTermToken", "none"),
        )
        self.data = self._scrape_data(start_date, *args)


class DummyTFAScraperNoOTP(OneZeroScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "dummy_tfa_no_otp.js")
    provider_name = "dummy_tfa_no_otp"
    requires_2fa = True

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Dummy TFA scraper

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials.get("email", "dummy@example.com"),
            self.credentials.get("password", "dummypass"),
            self.credentials.get("phoneNumber", "1234567890"),
            self.credentials.get("otpLongTermToken", "none"),
        )
        self.data = self._scrape_data(start_date, *args)


class DummyRegularScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "dummy_regular.js")
    provider_name = "dummy_regular"
    requires_2fa = False

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Dummy Regular scraper

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = ()
        self.data = self._scrape_data(start_date, *args)


class HapoalimScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "hapoalim.js")
    provider_name = "hapoalim"

    def scrape_data(self, start_date: str) -> None:
        """Get the data from the Hapoalim website.

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["userCode"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)

    def _handle_error(self, error: str):
        """Handle errors with Hapoalim-specific 2FA detection.

        Bank Hapoalim periodically requires 2FA (SMS verification) for
        sessions it considers unrecognized. The upstream library returns
        a GENERIC error when this happens because the 2FA page URL does
        not match any known login result. This override detects that
        scenario and provides actionable guidance.

        Parameters
        ----------
        error : str
            The error message from the scraping script's stderr.
        """
        original_error = error

        error_parts = error.split("logging error: ")
        parsed_error = error_parts[-1] if len(error_parts) > 1 else ""

        if not parsed_error:
            return

        # Detect 2FA-related errors for Hapoalim
        is_2fa = parsed_error.startswith(ErrorType.TWO_FACTOR_REQUIRED.value)

        # Also detect GENERIC/GENERAL errors from Hapoalim that are likely 2FA
        if not is_2fa and any(
            parsed_error.startswith(prefix)
            for prefix in ("GENERIC", "GENERAL_ERROR", "UNKNOWN_ERROR")
        ):
            lower_error = parsed_error.lower()
            tfa_indicators = [
                "navigation",
                "waiting for",
                "waitfor",
                "unexpected",
                "did not match",
            ]
            if any(indicator in lower_error for indicator in tfa_indicators):
                is_2fa = True

        if is_2fa:
            self.error = (
                "Two-factor authentication required by Bank Hapoalim. "
                "Log in to the bank website manually once to verify your "
                "device, then retry scraping."
            )
            self.error_type = ErrorType.TWO_FACTOR_REQUIRED.value
            raise TwoFactorRequiredError(self.error, original_error)

        # Fall back to the generic handler for all other errors
        super()._handle_error(error)


class LeumiScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "leumi.js")
    provider_name = "leumi"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Leumi website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class DiscountScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "discount.js")
    provider_name = "discount"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Discount website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["id"],
            self.credentials["password"],
            self.credentials["num"],
        )
        self.data = self._scrape_data(start_date, *args)


class MizrahiScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "mizrahi.js")
    provider_name = "mizrahi"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Mizrahi website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class MercantileScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "mercantile.js")
    provider_name = "mercantile"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Mercantile website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["id"],
            self.credentials["password"],
            self.credentials["num"],
        )
        self.data = self._scrape_data(start_date, *args)


class OtsarHahayalScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "otsar_hahayal.js")
    provider_name = "otsar hahayal"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Otsar Hahayal website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class UnionScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "union.js")
    provider_name = "union"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Union website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class BeinleumiScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "beinleumi.js")
    provider_name = "beinleumi"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Beinleumi website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class MassadScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "massad.js")
    provider_name = "massad"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Massad website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class YahavScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, "banks", "yahav.js")
    provider_name = "yahav"

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Yahav website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (
            self.credentials["username"],
            self.credentials["nationalID"],
            self.credentials["password"],
        )
        self.data = self._scrape_data(start_date, *args)


############################################
# Insurance Scrapers
############################################
class InsuranceScraper(Scraper):
    """Scraper base for insurance providers (currently a placeholder).

    Insurance scraping is not fully implemented; this class exists as a
    stub for future provider scrapers. ``script_path`` remains abstract.
    """

    service_name = "insurance"
    table_name = "insurance_data"
    table_unique_key = "id"
    sort_by_columns = "date"

    @property
    @abstractmethod
    def script_path(self) -> dict:
        """
        A dictionary containing the paths to the Node.js scripts for each provider
        """
        pass
