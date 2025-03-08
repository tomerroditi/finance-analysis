import pandas as pd
import datetime
import sqlite3
import os

from tests.conftest import DataFixtures
from fad.scraper.utils import save_to_db, scraped_data_to_df


last_month = datetime.datetime.now() - datetime.timedelta(days=30)
last_month_str = last_month.strftime('%Y-%m-%d')


class TestUtils(DataFixtures):
    @staticmethod
    def test_scraped_data_to_df():
        data = 'found 3 some other txt information bla blabla\n' \
               'account number: 1| type: my_type| id: my_id| date: 2024-02-03T22:00:00.000Z| amount: -500| desc: shop name| status: my_status\n' \
               'account number: 1| type: my_type| id: my_id_1| date: 2024-01-01T22:00:00.000Z| amount: -300| desc: some shop name| status: my_status\n' \
               'account number: 1| type: my_type| id: my_id_2| date: 2024-01-01T22:00:00.000Z| amount: -200| desc: some other shop name| status: my_status\n'

        df = scraped_data_to_df(data)
        assert df.shape == (3, 7)
        assert df['amount'].sum() == -1000
        assert df['type'].to_list() == ['my_type', 'my_type', 'my_type']
        assert df['id'].to_list() == ['my_id', 'my_id_1', 'my_id_2']
        assert df['date'].to_list() == [datetime.date(2024, 2, 3),
                                        datetime.date(2024, 1, 1),
                                        datetime.date(2024, 1, 1)]
        assert df['desc'].to_list() == ['shop name', 'some shop name', 'some other shop name']
        assert df['status'].to_list() == ['my_status', 'my_status', 'my_status']

    @staticmethod
    def test_scraped_data_to_df_no_transactions():
        data = 'found 0 some other txt information bla blabla\n'

        df = scraped_data_to_df(data)
        assert df.empty

    @staticmethod
    def test_save_to_db(fake_transactions_data_maker, tmpdir, monkeypatch):
        example_data = fake_transactions_data_maker()
        save_to_db(example_data, 'test_table', db_path=os.path.join(tmpdir, 'test.db'))
        conn = sqlite3.connect(os.path.join(tmpdir, 'test.db'))
        data = pd.read_sql('SELECT * FROM test_table', conn)
        assert data.shape == example_data.shape