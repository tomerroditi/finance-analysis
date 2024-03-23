import pandas as pd
import pytest
import datetime
import sqlite3
import os

from src.scraper.scrapers import get_isracard_data, get_max_data, scraped_data_to_df, save_to_db, pull_data


last_month = datetime.datetime.now() - datetime.timedelta(days=30)

@pytest.fixture(scope='function')
def ex_data(faker) -> pd.DataFrame:
    """create a fake data for testing the save_to_db function"""
    len = 10
    data = pd.DataFrame({'type': [faker.word() for _ in range(len)],
                         'id': [faker.word() for _ in range(len)],
                         'date': [faker.date_time_this_year() for _ in range(len)],
                         'amount': [faker.random_number() for _ in range(len)],
                         'desc': [faker.word() for _ in range(len)],
                         'status': [faker.word() for _ in range(len)]})
    return data


@pytest.mark.sensitive
def test_get_isracard_data():
    # get the data from the last month
    data = get_isracard_data(last_month)
    assert data.startswith('found ')
    # check that the number of lines in the output are as expected
    number_of_lines = int(data[:20].split(' ')[1])
    assert len(data.split('\n')) == number_of_lines + 2  # 1 for the first line and 1 for the last line which is empty


@pytest.mark.sensitive
def test_get_max_data():
    # get the data from the last month
    data = get_max_data(last_month)
    assert data.startswith('found ')
    # check that the number of lines in the output are as expected
    number_of_lines = int(data[:20].split(' ')[1])
    assert len(data.split('\n')) == number_of_lines + 2  # 1 for the first line and 1 for the last line which is empty


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


def test_save_to_db(ex_data, tmpdir, monkeypatch):
    # rename scrapers.src_file to the tmpdir
    monkeypatch.setattr('src.scraper.scrapers.src_file', os.path.join(tmpdir, 'test.txt'))
    # save the data to the db
    save_to_db(ex_data, 'test_table')


def test_pull_data(monkeypatch, tmpdir):
    # mock the get_isracard_data and get_max_data functions
    def mock_get_isracard_data(start_date):
        return 'found 3 some other txt information bla blabla\n' \
               'account number: 001| type: my_type| id: my_id| date: 2024-02-03T22:00:00.000Z| amount: -500| desc: shop name| status: my_status\n' \
               'account number: 001| type: my_type| id: my_id_1| date: 2024-01-01T22:00:00.000Z| amount: -300| desc: some shop name| status: my_status\n' \
               'account number: 001| type: my_type| id: my_id_2| date: 2024-01-01T22:00:00.000Z| amount: -200| desc: some other shop name| status: my_status\n'

    def mock_get_max_data(start_date):
        return 'found 3 some other txt information bla blabla\n' \
               'account number: 002| type: my_type| id: my_id| date: 2024-02-03T22:00:00.000Z| amount: -500| desc: shop name| status: my_status\n' \
               'account number: 002| type: my_type| id: my_id_1| date: 2024-01-01T22:00:00.000Z| amount: -300| desc: some shop name| status: my_status\n' \
               'account number: 002| type: my_type| id: my_id_2| date: 2024-01-01T22:00:00.000Z| amount: -200| desc: some other shop name| status: my_status\n'

    monkeypatch.setattr('src.scraper.scrapers.get_isracard_data', mock_get_isracard_data)
    monkeypatch.setattr('src.scraper.scrapers.get_max_data', mock_get_max_data)

    # mock the src_file path
    monkeypatch.setattr('src.scraper.scrapers.src_file', os.path.join(tmpdir, 'test.txt'))

    start_date = datetime.datetime(2021, 1, 1)
    pull_data(start_date)
    db_path = os.path.join(tmpdir, 'data.db')
    conn = sqlite3.connect(db_path)
    credit_cards_data = pd.read_sql('SELECT * FROM credit_card_transactions', conn)
    assert credit_cards_data.shape == (6, 7)
    assert credit_cards_data['amount'].sum() == -2000