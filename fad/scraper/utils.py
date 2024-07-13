import pandas as pd
import sqlite3

from datetime import datetime
from fad import DB_PATH
from fad.naming_conventions import TransactionsTableFields


def scraped_data_to_df(data: str) -> pd.DataFrame:
    """
    Convert the scraped data to a pandas DataFrame

    Parameters
    ----------
    data: str
        the scraped data in string format, should have the following format:
        'found N transactions for account number <account_number>\n'
        'key1: value1| key2: value2| ...| keyN: valueN\n'
        'key1: value1| key2: value2| ...| keyN: valueN\n'
        ...

        in case where no transactions were found, the data should be in the following format:
        'found 0 transactions for account number <account_number>\n'

    Returns
    -------
    pd.DataFrame
        the scraped data as a pandas DataFrame where the keys are the columns and the values are the rows. if no data
        was found, an empty DataFrame is returned

    """
    assert isinstance(data, str), 'data should be a string'

    data = data.split('\n')
    data = [line for line in data if not line.startswith('found ') and not line == '']
    if not data:
        return pd.DataFrame()
    data = [line.split('| ') for line in data]
    col_names = [item.split(': ')[0].replace(' ', '_') for item in data[0]]
    data = [[item.split(': ')[1] for item in line] for line in data]
    df = pd.DataFrame(data, columns=col_names)

    amount_col = TransactionsTableFields.AMOUNT.value
    date_col = TransactionsTableFields.DATE.value
    if amount_col in df.columns:
        df[amount_col] = df[amount_col].astype(float)
    if date_col in df.columns:
        df[date_col] = df[date_col].apply(lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ').date())
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
