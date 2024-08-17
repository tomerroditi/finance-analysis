import os
import subprocess
import pandas as pd
import datetime
import sqlite3

from abc import ABC, abstractmethod
from fad.scraper import NODE_JS_SCRIPTS_DIR
from fad.scraper.utils import save_to_db, scraped_data_to_df
from fad.naming_conventions import CreditCardTableFields, BankTableFields, Tables


class Scraper(ABC):
    """
    An abstract class to scrape data from different providers and save them to the database using Node.js scripts and
    pandas DataFrames.

    This class should be inherited by the specific scraper classes.

    Attributes
    ----------
    script_path : dict
        A dictionary containing the paths to the Node.js scripts for each provider
    table_name : str
        The name of the table to save the data to

    Methods
    -------
    pull_data_to_db(start_date: datetime.datetime | str, db_path: str = None)
        Pull data from the specified provider and save it to the database
    get_provider_scraping_function(provider: str)
        Get the scraping function for the specified provider
    """

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

    @property
    @abstractmethod
    def provider_scraping_function(self) -> dict:
        """
        A dictionary containing the scraping functions for each provider
        """
        pass

    def __init__(self, credentials: dict):
        """
        Initialize the Scraper object with the credentials to be used to log in to the websites

        Parameters
        ----------
        credentials : dict
            The credentials to log in to the website in the format of:
            {
             provider1:
                account1: {cred|_field1: value1, cred_field2: value2, ...},
                account2: {cred_field1: value1, cred_field2: value2, ...},
                ...
             provider2:
                account1: {cred_field1: value1, cred_field2: value2, ...},
                account2: {cred_field1: value1, cred_field2: value2, ...},
                ...
             }
        """
        self.credentials = credentials

    def pull_data_to_db(self, start_date: datetime.date | str, db_path: str = None):
        """
        Pull data from the specified provider and save it to the database

        Parameters
        ----------
        start_date : datetime.datetime
            The date from which to start pulling the data
        db_path : str
            The path to the database file. If None, the database file will be created in the folder of fad package
        """
        start_date = start_date.strftime('%Y-%m-%d') if isinstance(start_date, datetime.date) else start_date

        data = []
        for provider, accounts in self.credentials.items():
            scrape_func = self.get_provider_scraping_function(provider)
            for account_name, creds in accounts.items():
                scraped_data = scrape_func(start_date, **creds)
                scraped_data = self.add_account_name_and_provider_columns(scraped_data, account_name, provider)
                data.append(scraped_data)

        df = pd.concat(data, ignore_index=True)
        df = df.sort_values(by=self.sort_by_columns)
        df = self.add_missing_columns(df)
        save_to_db(df, self.table_name, db_path=db_path)

        self.drop_duplicates(db_path=db_path)

    def add_account_name_and_provider_columns(self, df: pd.DataFrame, account_name: str, provider: str) -> pd.DataFrame:
        """
        Add the account name and provider columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the account name and provider columns to
        account_name : str
            The account name to add to the DataFrame
        provider : str
            The provider to add to the DataFrame

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
        df[account_name_col] = account_name
        df[provider_col] = provider
        return df

    def add_missing_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add missing columns to the DataFrame

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to add the missing columns to
        """
        match self.table_name:
            case Tables.CREDIT_CARD.value:
                cols_to_add = [CreditCardTableFields.ID.value, CreditCardTableFields.STATUS.value,
                               CreditCardTableFields.CATEGORY.value, CreditCardTableFields.TAG.value]
            case Tables.BANK.value:
                cols_to_add = [BankTableFields.ID.value, BankTableFields.STATUS.value,
                               BankTableFields.CATEGORY.value, BankTableFields.TAG.value]
            case _:
                cols_to_add = []
        for col in cols_to_add:
            if col not in df.columns:
                df[col] = None
        return df

    def drop_duplicates(self, db_path: str):
        """
        Drop duplicates in the database

        Parameters
        ----------
        db_path : str
            The path to the database file.
        """
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(f"SELECT * FROM {self.table_name}", conn)
        df_unique = df.drop_duplicates()
        df_unique.to_sql(self.table_name, conn, if_exists='replace', index=False)
        conn.close()

    def get_provider_scraping_function(self, provider: str):
        """
        Get the scraping function for the specified provider

        Parameters
        ----------
        provider : str
            The provider to get the scraping function for
        """
        provider_scraping_function = self.provider_scraping_function
        try:
            func = provider_scraping_function[provider]
        except KeyError:
            raise ValueError(f'The provider {provider} is not supported yet. currently supporting: '
                             f'{", ".join(provider_scraping_function.keys())}')
        return func


class CreditCardScraper(Scraper):
    """
    A class to scrape credit card transactions from different providers and save them to the database using Node.js
    scripts and pandas DataFrames.
    """

    script_path = {
        'isracard': os.path.join(NODE_JS_SCRIPTS_DIR, 'isracard.js'),
        'max': os.path.join(NODE_JS_SCRIPTS_DIR, 'max.js'),
    }
    table_name = 'credit_card_transactions'
    table_unique_key = 'id'
    sort_by_columns = ['date', 'account_name', 'account_number']

    @property
    def provider_scraping_function(self) -> dict:
        """
        A dictionary containing the scraping functions for each provider
        """
        return {
            'isracard': self.get_isracard_data,
            'max': self.get_max_data
        }

    @staticmethod
    def get_isracard_data(start_date: str, id: str = None, card6Digits: str = None, password: str = None,
                          **kwargs) -> pd.DataFrame:
        """
        Get the data from the Isracard website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        id : str
            The owner's ID
        card6Digits : str
            The last 6 digits of the credit card
        password : str
            The password to log in to the website
        kwargs : dict
            Additional arguments, not used in this function
        """
        script_path = CreditCardScraper.script_path['isracard']
        result = subprocess.run(['node', script_path, id, card6Digits, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        df = scraped_data_to_df(result.stdout)
        return df

    @staticmethod
    def get_max_data(start_date: str, username: str = None, password: str = None, **kwargs) -> pd.DataFrame:
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
        script_path = CreditCardScraper.script_path['max']
        result = subprocess.run(['node', script_path, username, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        df = scraped_data_to_df(result.stdout)
        return df


class BankScraper(Scraper):
    """
    A class to scrape credit card transactions from different providers and save them to the database using Node.js
    scripts and pandas DataFrames.

    Currently, the functionality of the bank scrapers is very similar to the credit card scrapers, but we keep them
    separate for easier maintenance and future development.
    """

    script_path = {
        'onezero': os.path.join(NODE_JS_SCRIPTS_DIR, 'onezero.js'),
        'hapoalim': os.path.join(NODE_JS_SCRIPTS_DIR, 'hapoalim.js'),
    }
    table_name = 'bank_transactions'
    table_unique_key = 'id'
    sort_by_columns = ['date', 'account_name', 'account_number']

    @property
    def provider_scraping_function(self) -> dict:
        """
        A dictionary containing the scraping functions for each provider
        """
        return {
            'onezero': self.get_onezero_data,
            'hapoalim': self.get_hapoalim_data
        }

    @staticmethod
    def get_onezero_data(start_date: str, email: str = None, password: str = None,
                         phoneNumber: str = None, otpLongTermToken: str = None, **kwargs) -> pd.DataFrame:
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
        script_path = BankScraper.script_path['onezero']
        result = subprocess.run(['node', script_path, email, password,
                                 otpLongTermToken, phoneNumber, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        df = scraped_data_to_df(result.stdout)
        return df

    @staticmethod
    def get_hapoalim_data(start_date: str, userCode: str = None, password: str = None, **kwargs) -> (
            pd.DataFrame):
        """
        Get the data from the Hapoalim website

        Parameters
        ----------
        start_date : str
            The date from which to start pulling the data, should be in the format of 'YYYY-MM-DD'
        userCode : str
            The user code to log in to the website
        password : str
            The password to log in to the website
        """
        script_path = BankScraper.script_path['hapoalim']
        result = subprocess.run(['node', script_path, userCode, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        df = scraped_data_to_df(result.stdout)
        return df


class InsuranceScraper(Scraper):
    """
    A class to scrape insurance data from different providers and save them to the database using Node.js scripts and
    pandas DataFrames.
    """

    script_path = {}
    table_name = 'insurance_data'
    table_unique_key = 'id'
    sort_by_columns = 'date'

    @property
    def provider_scraping_function(self) -> dict:
        """
        A dictionary containing the scraping functions for each provider
        """
        raise NotImplementedError('The InsuranceScraper class is not implemented yet')
