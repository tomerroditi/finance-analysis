import os
import subprocess
import pandas as pd
import datetime
import sqlite3
import yaml

from time import sleep
from threading import Event
from abc import ABC, abstractmethod
from fad.scraper.exceptions import LoginError
from fad.scraper import NODE_JS_SCRIPTS_DIR
from fad.scraper.utils import save_to_db, scraped_data_to_df
from fad.app.naming_conventions import CreditCardTableFields, BankTableFields, Tables
from fad import CREDENTIALS_PATH


def get_scraper(service_name: str, provider_name: str, account_name: str, credentials: dict):
    """
    Get the scraper object for the specified service and provider

    Parameters
    ----------
    service_name : str
        The name of the service of the scraper. banks, credit_cards, insurance, etc.
    provider_name : str
        The name of the provider of the scraper. isracard, hapoalim, max, etc.
    account_name : str
        The name of the account to log the data into the database. used to allow multiple accounts for the same provider
    credentials : dict
        A dictionary containing the credentials to log in to the websites

    Returns
    -------
    Scraper
        The scraper object for the specified service and provider
    """
    if service_name == 'credit_cards':
        if provider_name == 'isracard':
            return IsracardScraper(account_name, credentials)
        elif provider_name == 'max':
            return MaxScraper(account_name, credentials)
    elif service_name == 'banks':
        if provider_name == 'onezero':
            return OneZeroScraper(account_name, credentials)
        elif provider_name == 'hapoalim':
            return HapoalimScraper(account_name, credentials)
    elif service_name == 'insurance':
        return InsuranceScraper(account_name, credentials)
    else:
        raise ValueError(f'The service name {service_name} is not supported yet.')


class Scraper(ABC):
    """
    An abstract class to scrape data from different providers and save them to the database using Node.js scripts and
    pandas DataFrames.

    This class should be inherited by the specific scraper classes.

    Attributes
    ----------
    service_name : str
        The name of the service of the scraper. banks, credit_cards, insurance, etc.
    provider_name : str
        The name of the provider of the scraper. isracard, hapoalim, max, etc.
    account_name : str
        The name of the account to log the data into the database. used to allow multiple accounts for the same provider
    credentials : dict
        A dictionary containing the credentials to log in to the websites
    script_path : str
        The path to the Node.js script to scrape the data
    table_name : str
        The name of the table to save the data to in the database
    table_unique_key : str
        The unique key in the table which is used to identify duplicated rows
    sort_by_columns : list[str]
        The columns to sort the data by in the database to maintain consistency
    """
    requires_2fa = False

    def __init__(self, account_name: str, credentials: dict):
        """
        Initialize the Scraper object with the credentials to be used to log in to the websites

        Parameters
        ----------
        account_name : str
            The name of the account to use to log data into the database
        credentials : dict
            A dictionary containing the credentials to log in to the websites

        """
        self.account_name = account_name
        self.credentials = credentials
        self.process = None
        self.result = ''
        self.error = ''
        self.data = None

        # 2fa related attributes
        self.otp_code = None
        self.otp_event = Event()

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

    def pull_data_to_db(self, start_date: datetime.date | str, db_path: str = None):
        """
        Pull data from the specified provider and save it to the database

        Parameters
        ----------
        start_date : datetime.datetime
            The date from which to start pulling the data
        db_path : str
            The path to the database file. If None, the data will be saved in the app default database which is at
            fad.resources.data.db
        """
        start_date = start_date.strftime('%Y-%m-%d') if isinstance(start_date, datetime.date) else start_date

        try:
            self.scrape_data(start_date)
        except LoginError as e:
            print(f'{self.provider_name}: {self.account_name}: {e}')
            return

        if self.data.empty:
            print(f'{self.provider_name}: {self.account_name}: No transactions found')
            return

        self.data = self.data.sort_values(by=self.sort_by_columns)
        self.data = self._add_account_name_and_provider_columns(self.data)
        self.data = self._add_missing_columns(self.data)
        # TODO: improve the saving protocol, make the id column the primary key and add a check for duplicates
        save_to_db(self.data, self.table_name, db_path=db_path)

        self._drop_duplicates(db_path=db_path, id_col=self.table_unique_key)

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
        args = ['node', self.script_path, *args, start_date]
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        self.result = result.stdout
        self.error = result.stderr
        self._handle_error(self.error)
        data = scraped_data_to_df(self.result)
        return data

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
                raise ValueError(f'The table name {self.table_name} is not supported yet.')
        df[account_name_col] = self.account_name
        df[provider_col] = self.provider_name
        return df

    def _drop_duplicates(self, db_path: str, id_col: str):
        """
        Drop duplicates in the database

        Parameters
        ----------
        db_path : str
            The path to the database file.
        """
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(f"SELECT * FROM {self.table_name}", conn)
        df_unique = df.drop_duplicates(subset=id_col)
        df_unique.to_sql(self.table_name, conn, if_exists='replace', index=False)
        conn.close()

    @abstractmethod
    def _add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add missing columns to the DataFrame to align all the scrapers

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the missing columns to
        """
        # TODO: is this necessary?
        pass

    @staticmethod
    def _handle_error(error: str):
        """
        Handle the error message from the scraping script. this is the most generic way to handle errors, each scraper
        should implement its own error handling method since the error messages can be different for each provider.

        Parameters
        ----------
        error: str
            The error message from the scraping script

        Raises
        ------
        LoginError
            If an error occurs during the scraping process
        """
        if error:
            raise LoginError(error)

    def _update_credentials_file(self):
        """
        Update the credentials file with the new OTP long-term token
        """
        with open(CREDENTIALS_PATH, 'r') as file:
            credentials = yaml.safe_load(file)

        credentials[self.service_name][self.provider_name][self.account_name] = self.credentials

        with open(CREDENTIALS_PATH, 'w') as file:
            yaml.dump(credentials, file)

    def set_otp_code(self, otp_code):
        """
        Set the OTP code to be used for the 2FA process. is used only by scrapers that require 2FA. calling this method
        will notify the scraper that the OTP code is available and will continue the scraping process.

        Parameters
        ----------
        otp_code : str
            The OTP (One-Time Password) code to be used for the 2FA process

        Returns
        -------
        None
        """
        self.otp_code = otp_code
        self.otp_event.set()  # Notify that the OTP code is available


############################################
# Credit Card Scrapers
############################################
class CreditCardScraper(Scraper, ABC):
    service_name = 'credit_cards'
    table_name = 'credit_card_transactions'
    table_unique_key = 'id'
    sort_by_columns = ['date']

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
        cols_to_add = [CreditCardTableFields.ID.value, CreditCardTableFields.STATUS.value,
                       CreditCardTableFields.CATEGORY.value, CreditCardTableFields.TAG.value]

        for col in cols_to_add:
            if col not in df.columns:
                df[col] = None
        return df


class IsracardScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, 'isracard.js')
    provider_name = 'isracard'

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Isracard website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["id"], self.credentials["card6Digits"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


class MaxScraper(CreditCardScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, 'max.js')
    provider_name = 'max'

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Max website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        username : str
            The username to log in to the website
        password : str
            The password to log in to the website
        kwargs : dict
            Additional arguments, not used in this function
        """
        args = (self.credentials["username"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


############################################
# Bank Scrapers
############################################
class BankScraper(Scraper, ABC):
    service_name = 'banks'
    table_name = 'bank_transactions'
    table_unique_key = 'id'
    sort_by_columns = ['date']

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
        cols_to_add = [BankTableFields.ID.value, BankTableFields.STATUS.value,
                       BankTableFields.CATEGORY.value, BankTableFields.TAG.value]

        for col in cols_to_add:
            if col not in df.columns:
                df[col] = None
        return df


class OneZeroScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, 'onezero.js')
    provider_name = 'onezero'
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
            self.credentials.get("otpLongTermToken", "none")
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
        """
        args = ['node', self.script_path, *args, start_date]
        self.process = subprocess.Popen(args,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        encoding='utf-8')

        # wait for the OTP code to be requested, and then send it
        lines = []
        while True:
            output = self.process.stdout.readline()
            if output:
                lines.append(output)
                if 'Enter OTP code:' in output:
                    self.otp_code = "waiting for input"
                    self.otp_event.wait()  # Wait until the OTP code is set
                    self.process.stdin.write(self.otp_code + '\n')
                    self.process.stdin.flush()
                    process.stdin.close()
                    break
                elif 'writing scraped data to console' in output:  # long term token is valid
                    self.otp_code = "not required"
                    break
            sleep(0.3)

        while self.process.poll() is None:  # wait for the process to finish
            sleep(0.5)
        self.result, self.error = self.process.communicate()

        if self.error:
            raise LoginError(self.error)

        lines = self.result.split('\n')
        for line in lines:
            if 'renewed long term token' in line:
                self.credentials['otpLongTermToken'] = line.split(':', 1)[-1].strip()
                self._update_credentials_file()
                break
            elif 'long term token is valid' in line:
                break

        return scraped_data_to_df(self.result)


class HapoalimScraper(BankScraper):
    script_path = os.path.join(NODE_JS_SCRIPTS_DIR, 'hapoalim.js')
    provider_name = 'hapoalim'

    def scrape_data(self, start_date: str) -> None:
        """
        Get the data from the Max website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        """
        args = (self.credentials["userCode"], self.credentials["password"])
        self.data = self._scrape_data(start_date, *args)


############################################
# Insurance Scrapers
############################################
class InsuranceScraper(Scraper):
    service_name = 'insurance'
    table_name = 'insurance_data'
    table_unique_key = 'id'
    sort_by_columns = 'date'

    @property
    @abstractmethod
    def script_path(self) -> dict:
        """
        A dictionary containing the paths to the Node.js scripts for each provider
        """
        pass
