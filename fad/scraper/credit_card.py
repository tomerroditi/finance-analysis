import subprocess
import pandas as pd
import datetime

from pathlib import Path
from fad.scraper.utils import save_to_db, scraped_data_to_df


class CreditCardScraper:
    """
    A class to scrape credit card transactions from different providers and save them to the database using Node.js
    scripts and pandas DataFrames.
    """

    script_path = {
        'isracard': Path(__file__).parent / 'node/isracard.js',
        'max': Path(__file__).parent / 'node/max.js'
    }

    def __init__(self, credentials: dict):
        """
        Initialize the CreditCardScraper object with the credentials to be used to log in to the websites

        Parameters
        ----------
        credentials : dict
            The credit cards credentials to log in to the website in the format of:
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
        save_to_db(df, 'credit_card_transactions', db_path=db_path)

    def get_provider_scraping_function(self, provider: str):
        """
        Get the scraping function for the specified provider

        Parameters
        ----------
        provider : str
            The provider to get the scraping function for
        """
        assert isinstance(provider, str), 'provider should be a string'

        match provider:
            case 'isracard':
                return self.get_isracard_data
            case 'max':
                return self.get_max_data
            case _:
                raise ValueError('currently only supporting Isracard and Max providers')

    @staticmethod
    def get_isracard_data(start_date: str, id: str = None, card6Digits: str = None, password: str = None,
                          **kwargs) -> (
            pd.DataFrame):
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
