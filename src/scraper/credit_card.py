import subprocess
import pandas as pd
import datetime
import sqlite3
import yaml

from pathlib import Path
from src import __file__ as src_file


# TODO: exchange the python file that hold the credentials with a yaml file
def get_isracard_data(credentials: dict, start_date: datetime.datetime) -> str:
    """
    Get the data from the Isracard website

    Parameters
    ----------
    credentials : dict
        The credentials to log in to the website, should contain the following keys: 'id', 'card6Digits', 'password'
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    start_date = start_date.strftime('%Y-%m-%d')
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/isracard.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, credentials['id'], credentials['card6Digits'],
                             credentials['password'], start_date],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout.split('\n')[0])
    return result.stdout


def get_max_data(credentials: dict, start_date: datetime.datetime) -> str:
    """
    Get the data from the Max website

    Parameters
    ----------
    credentials : dict
        The credentials to log in to the website, should contain the following keys: 'username', 'password'
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    start_date = start_date.strftime('%Y-%m-%d')
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/max.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, credentials['username'], credentials['password'], start_date],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout.split('\n')[0])
    return result.stdout


def scraped_data_to_df(data: str) -> pd.DataFrame:
    assert isinstance(data, str), 'data should be a string'

    data = data.split('\n')
    data = [line for line in data if not line.startswith('found ') or not line == '']
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

    with open('../credentials.yaml') as file:
        credentials = yaml.load(file, Loader=yaml.FullLoader)
    credentials = credentials['credit_cards']

    isracard_data = get_isracard_data(credentials['isracard'], start_date)
    max_data = get_max_data(credentials['max'], start_date)

    isracard_df = scraped_data_to_df(isracard_data)
    max_df = scraped_data_to_df(max_data)

    save_to_db(isracard_df, 'credit_card_transactions')
    save_to_db(max_df, 'credit_card_transactions')



