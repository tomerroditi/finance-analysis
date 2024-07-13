import pandas as pd
import sqlite3

from datetime import datetime
from fad import DB_PATH


def scraped_data_to_df(data: str) -> pd.DataFrame:
    assert isinstance(data, str), 'data should be a string'

    data = data.split('\n')
    data = [line for line in data if not line.startswith('found ') and not line == '']
    data = [line.split('| ') for line in data]
    col_names = [item.split(': ')[0] for item in data[0]]
    data = [[item.split(': ')[1] for item in line] for line in data]
    df = pd.DataFrame(data, columns=col_names)
    if 'amount' in df.columns:
        df['amount'] = df['amount'].astype(float)
    if 'date' in df.columns:
        df['date'] = df['date'].apply(lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'))
    return df


def save_to_db(df: pd.DataFrame, table_name: str, db_path: str = None) -> None:
    """
    Save the data to the database

    Parameters
    ----------
    df: pd.DataFrame
        the data to save to the database
    table_name: str
        the name of the table to save the data to
    db_path: str
        the path to the database file. If None, the database file will be created in the folder of fad package with
        the name 'data.db'

    Returns
    -------

    """
    assert isinstance(df, pd.DataFrame), 'df should be a pandas DataFrame object'
    assert isinstance(table_name, str), 'table_name should be a string'

    db_path = DB_PATH if db_path is None else db_path
    conn = sqlite3.connect(db_path)
    df.to_sql(table_name, conn, if_exists='append', index=False)
    # delete duplicates
    conn.commit()
    conn.close()
    print(f'Successfully saved the data to the {table_name} table in the database')
