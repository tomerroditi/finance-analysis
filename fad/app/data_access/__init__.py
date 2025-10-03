import os

import streamlit as st
from streamlit.connections import SQLConnection

from fad import DB_PATH
from fad.app.data_access.transactions_repository import TransactionsRepository


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
