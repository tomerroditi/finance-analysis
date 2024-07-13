import pytest
import sqlite3
import os
import yaml
import pandas as pd

from fad import DB_PATH, CREDENTIALS_PATH
from typing import Callable


class ConnFixtures:
    @pytest.fixture(scope='session')
    def db_conn(self):
        """return a connection to the app database"""
        conn = sqlite3.connect(DB_PATH)
        yield conn
        conn.close()

    @pytest.fixture(scope='session')
    def demo_db_conn(self, demo_transactions_data):
        """create a demo db with fake data and return a connection to it"""
        conn = sqlite3.connect(':memory:')
        demo_transactions_data.to_sql('credit_card_transactions', conn, index=False)
        yield conn
        conn.close()

    @pytest.fixture(scope='session')
    def empty_db_conn(self):
        """return a connection to an empty database"""
        conn = sqlite3.connect(':memory:')
        yield conn
        conn.close()


class DataFixtures:
    @pytest.fixture(scope='session')
    def credentials(self) -> dict:
        """returns a set of real credentials for the tests to use for scraping"""
        with open(CREDENTIALS_PATH, 'r') as file:
            creds = yaml.safe_load(file)
        return creds

    @pytest.fixture(scope='session')
    def fake_credentials(self) -> dict:
        """return a set of fake credentials for testing purposes"""
        return {'credit_cards': {'isracard': {'user1': {'id': 'my_id', 'card6Digits': '123456'},
                                              'user2': {'id': 'my_id', 'card6Digits': '123456'}},
                                 'max': {'user1': {'username': 'my_username', 'password': 'my_password'},
                                         'user2': {'username': 'my_username', 'password': 'my_password'}}},
                'banks': {'onezero': {'user1': {'email': 'my_email', 'password': 'my_password'},
                                      'user2': {'email': 'my_email', 'password': 'my_password'}},
                          'hapoalim': {'user1': {'id': 'my_id', 'password': 'my_password'}}}}

    @pytest.fixture(scope='session')
    def demo_transactions_data(self, fake_transactions_data_maker) -> pd.DataFrame:
        """create a fake data to demo the app with"""
        data = []
        for _ in range(10):
            data.append(fake_transactions_data_maker(30))
        data = pd.concat(data)
        return data

    @pytest.fixture(scope='function')
    def fake_transactions_data_maker(self, faker) -> Callable:
        """
        return a function that creates fake data for various testing purposes
        """
        def example_data(length: int = 10) -> pd.DataFrame:
            """create a fake data for testing the save_to_db function"""
            data = pd.DataFrame({'account_number': [faker.word()] * length,
                                 'type': [faker.word() for _ in range(length)],
                                 'id': [faker.word() for _ in range(length)],
                                 'date': [faker.date_time_this_year() for _ in range(length)],
                                 'amount': [faker.random_number() for _ in range(length)],
                                 'desc': [faker.word() for _ in range(length)],
                                 'status': [faker.word() for _ in range(length)]})
            return data
        return example_data
