import pytest
import datetime

from scraper.scrapers import get_isracard_data, get_max_data, scraped_data_to_df


def test_get_isracard_data():
    data = get_isracard_data()
    assert data.startswith('found ')
    # check that the number of lines in the output are as expected
    number_of_lines = int(data[:20].split(' ')[1])
    assert len(data.split('\n')) == number_of_lines + 2  # 1 for the first line and 1 for the last line which is empty


def test_get_max_data():
    data = get_max_data()
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


