import os
import subprocess
import pandas as pd
import datetime

from abc import ABC, abstractmethod
from fad.scraper import NODE_JS_SCRIPTS_DIR
from fad.scraper.utils import save_to_db, scraped_data_to_df


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

    def pull_data_to_db(self, start_date: datetime.datetime | str, db_path: str = None):
        """
        Pull data from the specified provider and save it to the database

        Parameters
        ----------
        start_date : datetime.datetime
            The date from which to start pulling the data
        db_path : str
            The path to the database file. If None, the database file will be created in the folder of fad package
        """
        start_date = start_date.strftime('%Y-%m-%d') if isinstance(start_date, datetime.datetime) else start_date

        data = []
        for provider, accounts in self.credentials.items():
            scrape_func = self.get_provider_scraping_function(provider)
            for account, creds in accounts.items():
                scraped_data = scrape_func(start_date, **creds)
                scraped_data['account'] = account
                data.append(scraped_data)

        df = pd.concat(data, ignore_index=True)
        save_to_db(df, self.table_name, db_path=db_path)

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
        # Run the Node.js script
        result = subprocess.run(['node', script_path, id, card6Digits, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        print(result.stdout.split('\n')[0])
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
        # Run the Node.js script
        result = subprocess.run(['node', script_path, username, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        print(result.stdout.split('\n')[0])
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
        # Run the Node.js script
        result = subprocess.run(['node', script_path, email, password,
                                 otpLongTermToken, phoneNumber, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        print(result.stdout.split('\n')[0])
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
        # Run the Node.js script
        result = subprocess.run(['node', script_path, userCode, password, start_date],
                                capture_output=True, text=True, encoding='utf-8')
        print(result.stdout.split('\n')[0])
        df = scraped_data_to_df(result.stdout)
        return df


class InsuranceScraper(Scraper):
    """
    A class to scrape insurance data from different providers and save them to the database using Node.js scripts and
    pandas DataFrames.
    """

    script_path = {}
    table_name = 'insurance_data'

    @property
    def provider_scraping_function(self) -> dict:
        """
        A dictionary containing the scraping functions for each provider
        """
        raise NotImplementedError('The InsuranceScraper class is not implemented yet')
