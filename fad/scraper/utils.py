import pandas as pd
import sqlite3

from datetime import datetime
from fad import DB_PATH
from fad.app.naming_conventions import TransactionsTableFields


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

    lines = data.strip().split('\n')
    if not lines or lines[0].startswith('found 0 transactions'):
        return pd.DataFrame()
    # Skip the first line (summary), process the rest
    data_lines = lines[1:]
    if not data_lines or all(not line.strip() for line in data_lines):
        return pd.DataFrame()
    # Split each line into key-value pairs
    parsed = []
    for line in data_lines:
        if not line.strip():
            continue
        try:
            items = [item for item in line.split('|') if item.strip()]
            row = {}
            for item in items:
                key_val = item.split(': ', 1)
                if len(key_val) != 2:
                    continue  # skip malformed
                key, val = key_val
                row[key.replace(' ', '_')] = val
            parsed.append(row)
        except Exception:
            continue  # skip malformed lines
    if not parsed:
        return pd.DataFrame()
    df = pd.DataFrame(parsed)

    amount_col = TransactionsTableFields.AMOUNT.value
    date_col = TransactionsTableFields.DATE.value
    if amount_col in df.columns:
        df[amount_col] = df[amount_col].astype(float)
    if date_col in df.columns:
        try:
            df[date_col] = df[date_col].apply(lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ').date())
        except ValueError:
            df[date_col] = df[date_col].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').date())
    return df


def save_to_db(df: pd.DataFrame, table_name: str, db_path: str = DB_PATH) -> None:
    """
    Save the data to the database

    Parameters
    ----------
    df: pd.DataFrame
        the data to save to the database
    table_name: str
        the name of the table to save the data to
    db_path: str
        the path to the database file. default to the global variable DB_PATH.
    """
    assert isinstance(df, pd.DataFrame), 'df should be a pandas DataFrame object'
    assert isinstance(table_name, str), 'table_name should be a string'

    conn = sqlite3.connect(db_path)
    df.to_sql(table_name, conn, if_exists='append', index=False)
    conn.commit()
    conn.close()
