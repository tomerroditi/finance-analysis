import subprocess
import pandas as pd
import datetime
import sqlite3

from pathlib import Path
from .credentials import isracard_credentials, max_credentials, onezero_credentials, hafenix_credentials
from src import __file__ as src_file


def get_isracard_data(start_date: datetime.datetime) -> str:
    """
    Get the data from the Isracard website

    Parameters
    ----------
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    start_date = start_date.strftime('%Y-%m-%d')
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/isracard.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, isracard_credentials['id'], isracard_credentials['card6Digits'],
                             isracard_credentials['password'], start_date],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout.split('\n')[0])
    return result.stdout


def get_max_data(start_date: datetime.datetime) -> str:
    """
    Get the data from the Max website

    Parameters
    ----------
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    start_date = start_date.strftime('%Y-%m-%d')
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/max.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, max_credentials['username'], max_credentials['password'], start_date],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout.split('\n')[0])
    return result.stdout


def get_onezero_data():
    pass


def get_hafenixa_data():
    pass


def scraped_data_to_df(data: str) -> pd.DataFrame:
    assert isinstance(data, str), 'data should be a string'

    data = data.split('\n')
    if data[0].startswith('found '):
        data = data[1:]
    if data[-1] == '':
        data = data[:-1]
    data = [line.split('| ') for line in data]
    col_names = [item.split(': ')[0] for item in data[0]]
    data = [[item.split(': ')[1] for item in line] for line in data]
    df = pd.DataFrame(data, columns=col_names)
    if 'amount' in df.columns:
        df['amount'] = df['amount'].astype(float)
    if 'date' in df.columns:
        df['date'] = df['date'].apply(lambda x: datetime.datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'))
    return df


def save_to_db(df: pd.DataFrame, table_name: str) -> None:
    assert isinstance(df, pd.DataFrame), 'df should be a pandas DataFrame object'
    assert isinstance(table_name, str), 'table_name should be a string'

    db_path = Path(src_file).parent / 'data.db'
    conn = sqlite3.connect(db_path)
    df.to_sql(table_name, conn, if_exists='append', index=False)
    # delete duplicates
    conn.execute(f"DELETE FROM {table_name} WHERE rowid NOT IN (SELECT MIN(rowid) FROM {table_name} GROUP BY id)")
    conn.commit()
    conn.close()
    print(f'Successfully saved the data to the {table_name} table in the database')


def pull_data(start_date: datetime.datetime):
    """
    Pull data from all the sources and save it to the database

    Parameters
    ----------
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    isracard_data = get_isracard_data(start_date)
    max_data = get_max_data(start_date)
    # onezero_data = get_onezero_data()
    # hafenixa_data = get_hafenixa_data()
    isracard_df = scraped_data_to_df(isracard_data)
    max_df = scraped_data_to_df(max_data)
    # onezero_df = scraped_data_to_df(onezero_data)
    # hafenixa_df = scraped_data_to_df(hafenixa_data)
    save_to_db(isracard_df, 'credit_card_transactions')
    save_to_db(max_df, 'credit_card_transactions')
    # save_to_db(onezero_df, 'bank_transactions')
    # save_to_db(hafenixa_df, 'finance_transactions


