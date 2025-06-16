import os
import sqlalchemy
import pandas as pd
import streamlit as st

from streamlit.connections import SQLConnection
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad import DB_PATH


def get_db_connection() -> SQLConnection:
    """
    Get a connection to the database

    Returns
    -------
    SQLConnection
        The connection to the app database
    """
    if 'conn' not in st.session_state:
        if not os.path.exists(DB_PATH):
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(DB_PATH, 'w'):
                pass

        st.session_state['conn'] = st.connection('data', 'sql')
    return st.session_state['conn']


def get_table(conn: SQLConnection, table_name: str) -> pd.DataFrame:
    """
    Get the data from the given table

    Parameters
    ----------
    conn : SQLConnection
        The connection to the database
    table_name : str
        The name of the table to get the data from

    Returns
    -------
    pd.DataFrame
        The data from the table
    """
    try:
        return conn.query(f'SELECT * FROM {table_name};', ttl=0)
    except sqlalchemy.exc.OperationalError:
        return pd.DataFrame()
