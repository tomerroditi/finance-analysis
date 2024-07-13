import pandas as pd
import pytest
import datetime
import sqlite3
import os

from tests.conftest import DataFixtures
from fad.scraper.scrapers import CreditCardScraper, BankScraper
from fad.scraper.bank import BankScraper
from fad.scraper.utils import save_to_db, scraped_data_to_df


last_month = datetime.datetime.now() - datetime.timedelta(days=30)
last_month_str = last_month.strftime('%Y-%m-%d')


class TestUtils(DataFixtures):
    @staticmethod
    def test_scraped_data_to_df():
        data = 'found 3 some other txt information bla blabla\n' \
               'type: my_type| id: my_id| date: 2024-02-03T22:00:00.000Z| amount: -500| desc: shop name| status: my_status\n' \
               'type: my_type| id: my_id_1| date: 2024-01-01T22:00:00.000Z| amount: -300| desc: some shop name| status: my_status\n' \
               'type: my_type| id: my_id_2| date: 2024-01-01T22:00:00.000Z| amount: -200| desc: some other shop name| status: my_status\n'

        df = scraped_data_to_df(data)
        assert df.shape == (3, 6)
        assert df['amount'].sum() == -1000
        assert df['type'].to_list() == ['my_type', 'my_type', 'my_type']
        assert df['id'].to_list() == ['my_id', 'my_id_1', 'my_id_2']
        assert df['date'].to_list() == [datetime.datetime(2024, 2, 3, 22, 0),
                                        datetime.datetime(2024, 1, 1, 22, 0),
                                        datetime.datetime(2024, 1, 1, 22, 0)]
        assert df['desc'].to_list() == ['shop name', 'some shop name', 'some other shop name']
        assert df['status'].to_list() == ['my_status', 'my_status', 'my_status']

    @staticmethod
    def test_save_to_db(fake_transactions_data_maker, tmpdir, monkeypatch):
        example_data = fake_transactions_data_maker()
        save_to_db(example_data, 'test_table', db_path=os.path.join(tmpdir, 'test.db'))
        conn = sqlite3.connect(os.path.join(tmpdir, 'test.db'))
        data = pd.read_sql('SELECT * FROM test_table', conn)
        assert data.shape == example_data.shape


class TestCreditCardScraper(DataFixtures):
    @staticmethod
    @pytest.mark.sensitive
    def test_get_isracard_data(credentials):
        data = CreditCardScraper.get_isracard_data(last_month_str, **credentials['credit_cards']['isracard']['Tomer'])
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0

    @staticmethod
    @pytest.mark.sensitive
    def test_get_max_data(credentials):
        data = CreditCardScraper.get_max_data(last_month_str, **credentials['credit_cards']['max']['Tomer'])
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0

    @staticmethod
    def test_pull_data(monkeypatch, tmpdir, fake_transactions_data_maker):
        # mock the get_isracard_data and get_max_data functions
        def mock_get_isracard_data(*args, **kwargs):
            return fake_transactions_data_maker(10)

        def mock_get_max_data(*args, **kwargs):
            return fake_transactions_data_maker(3)

        credentials = {
            'isracard': {
                'some_name': {'id': '123456789', 'card6Digits': '123456'}
            },
            'max': {
                'other_name': {'username': 'tomer', 'password': '123456'}
            }
        }

        credit_card_scraper = CreditCardScraper(credentials)
        monkeypatch.setattr(credit_card_scraper, 'get_isracard_data', mock_get_isracard_data)
        monkeypatch.setattr(credit_card_scraper, 'get_max_data', mock_get_max_data)

        start_date = datetime.datetime(2021, 1, 1)
        db_path = os.path.join(tmpdir, 'data.db')

        credit_card_scraper.pull_data_to_db(start_date, db_path)
        conn = sqlite3.connect(db_path)
        credit_cards_data = pd.read_sql('SELECT * FROM credit_card_transactions', conn)
        assert credit_cards_data.shape == (13, 8)


class TestBankScraper(DataFixtures):
    @staticmethod
    @pytest.mark.sensitive
    def test_get_onezero_data(credentials):
        data = BankScraper.get_onezero_data(last_month_str, **credentials['banks']['onezero']['Tomer'])
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0

    @staticmethod
    @pytest.mark.sensitive
    def test_get_hapoalim_data(credentials):
        data = BankScraper.get_hapoalim_data(last_month_str, **credentials['banks']['hapoalim']['Shir'])
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0

    @staticmethod
    def test_pull_data(monkeypatch, tmpdir, fake_transactions_data_maker):
        # mock the get_isracard_data and get_max_data functions
        def mock_get_onezero_data(*args, **kwargs):
            return fake_transactions_data_maker(5)

        credentials = {
            'onezero': {
                'some_name': {'id': '123456789', 'card6Digits': '123456', 'otplongtermtoken': '123456'}
            },
        }

        credit_card_scraper = BankScraper(credentials)
        monkeypatch.setattr(credit_card_scraper, 'get_onezero_data', mock_get_onezero_data)

        db_path = os.path.join(tmpdir, 'data.db')

        credit_card_scraper.pull_data_to_db(last_month, db_path)
        conn = sqlite3.connect(db_path)
        credit_cards_data = pd.read_sql('SELECT * FROM credit_card_transactions', conn)
        assert credit_cards_data.shape == (5, 8)
