import sqlite3
from datetime import datetime

import pandas as pd

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

    data = data.split('\n')
    data = [line for line in data if line.startswith("account number:")]
    if not data:
        return pd.DataFrame()
    data = [line.split('| ') for line in data]
    col_names = [item.split(': ')[0].replace(' ', '_') for item in data[0]]
    data = [[item.split(': ')[1] for item in line] for line in data]
    df = pd.DataFrame(data, columns=col_names)

    amount_col = TransactionsTableFields.AMOUNT.value
    date_col = TransactionsTableFields.DATE.value
    if amount_col in df.columns:  # convert to float
        df[amount_col] = df[amount_col].astype(float)
    if date_col in df.columns:  # convert to string of format 'YYYY-MM-DD'
        try:
            df[date_col] = df[date_col].apply(lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d'))
        except ValueError:
            df[date_col] = df[date_col].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').strftime('%Y-%m-%d'))
    return df
