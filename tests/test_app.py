import datetime

from unittest.mock import patch
from tests.conftest import ConnFixtures, DataFixtures
from fad.app import utils


class TestDataUtils(ConnFixtures, DataFixtures):
    def test_pull_data(self, fake_credentials):
        """check that the pull_data_to|_db is called properly"""
        # monkeypatch the pull_data_to_db function of the BankScraper and CreditCardScraper classes
        with patch('fad.scraper.bank.BankScraper.pull_data_to_db') as bank_mock, \
             patch('fad.scraper.credit_card.CreditCardScraper.pull_data_to_db') as credit_card_mock:
            # Set the mocks to return None immediately
            bank_mock.return_value = None
            credit_card_mock.return_value = None

            last_month = datetime.datetime.now() - datetime.timedelta(days=30)
            utils.DataUtils.pull_data_from_all_scrapers_to_db(last_month, fake_credentials)

            assert bank_mock.call_count == 1
            assert credit_card_mock.call_count == 1

    def test_get_latest_data_date_db_with_data(self, db_conn):
        date = utils.DataUtils.get_latest_data_date(db_conn)
        assert isinstance(date, datetime.date)

    def test_get_latest_data_date_empty_db(self, empty_db_conn):
        date = utils.DataUtils.get_latest_data_date(empty_db_conn)
        assert date == datetime.datetime.today() - datetime.timedelta(days=365)

