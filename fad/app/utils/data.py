import streamlit as st
import yaml
import time
import sqlite3
import sqlalchemy
import pandas as pd
import numpy as np
from sqlalchemy.sql import text
from threading import Thread

from streamlit.connections import SQLConnection
from datetime import datetime, timedelta
from fad.scraper import get_scraper, Scraper
from fad import CATEGORIES_PATH
from fad.app.naming_conventions import (
    CreditCardTableFields,
    Tables,
    BankTableFields,
    TagsTableFields,
)


tags_table = Tables.TAGS.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
tags_category_col = TagsTableFields.CATEGORY.value
tag_col = TagsTableFields.TAG.value
tags_name_col = TagsTableFields.NAME.value
tags_service_col = TagsTableFields.SERVICE.value
tags_account_number_col = TagsTableFields.ACCOUNT_NUMBER.value
cc_desc_col = CreditCardTableFields.DESCRIPTION.value
cc_tag_col = CreditCardTableFields.TAG.value
cc_category_col = CreditCardTableFields.CATEGORY.value
cc_name_col = CreditCardTableFields.DESCRIPTION.value
cc_id_col = CreditCardTableFields.ID.value
cc_date_col = CreditCardTableFields.DATE.value
cc_provider_col = CreditCardTableFields.PROVIDER.value
cc_account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
cc_account_number_col = CreditCardTableFields.ACCOUNT_NUMBER.value
cc_amount_col = CreditCardTableFields.AMOUNT.value
bank_desc_col = BankTableFields.DESCRIPTION.value
bank_tag_col = BankTableFields.TAG.value
bank_category_col = BankTableFields.CATEGORY.value
bank_name_col = BankTableFields.DESCRIPTION.value
bank_id_col = BankTableFields.ID.value
bank_account_number_col = BankTableFields.ACCOUNT_NUMBER.value
bank_date_col = BankTableFields.DATE.value
bank_provider_col = BankTableFields.PROVIDER.value
bank_account_name_col = BankTableFields.ACCOUNT_NAME.value
bank_amount_col = BankTableFields.AMOUNT.value



def get_db_connection() -> SQLConnection:
    """
    Get a connection to the database

    Returns
    -------
    SQLConnection
        The connection to the app database
    """
    if 'conn' not in st.session_state:
        st.session_state['conn'] = st.connection('data', 'sql')
    return st.session_state['conn']


def assure_tags_table(conn: SQLConnection):
    """create the tags table if it doesn't exist"""
    with conn.session as s:
        s.execute(
            text(f'CREATE TABLE IF NOT EXISTS {tags_table} ({tags_name_col} TEXT PRIMARY KEY, {tags_category_col}'
                 f' TEXT, {tag_col} TEXT, {tags_service_col} TEXT, {tags_account_number_col} TEXT);'))
        s.commit()


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


def get_categories_and_tags() -> dict:
    """
    Get the categories and tags from the yaml file

    Returns
    -------
    dict
        The categories and tags dictionary
    """
    if 'categories_and_tags' not in st.session_state:
        with open(CATEGORIES_PATH, 'r') as file:
            st.session_state['categories_and_tags'] = yaml.load(file, Loader=yaml.FullLoader)
    return st.session_state['categories_and_tags']


def pull_data(start_date: datetime | str, credentials: dict, db_path: str | None = None) -> None:
    """
    Pull data from the data sources, from the given date to present, and save it to the database file.

    Parameters
    ----------
    start_date : datetime | str
        The date from which to start pulling the data
    credentials : dict
        The credentials dictionary
    db_path : str
        The path to the database file. If None the database file will be created in the folder of fad package
        with the name 'data.db'

    Returns
    -------
    None
    """
    if "pulled_data_from" not in st.session_state:
        st.session_state.pulled_data_from = {}
        st.session_state.pulled_data_status = {}

    for service, providers in credentials.items():
        if service not in st.session_state.pulled_data_from:
            st.session_state.pulled_data_from[service] = {}
        for provider, accounts in providers.items():
            if provider not in st.session_state.pulled_data_from[service]:
                st.session_state.pulled_data_from[service][provider] = []
            for account, credentials in accounts.items():
                if account in st.session_state.pulled_data_from[service][provider]:
                    st.session_state.pulled_data_status[f"{service}_{provider}_{account}"]  # noqa
                    continue
                st.session_state.pulled_data_from[service][provider].append(account)
                scraper = get_scraper(service, provider, account, credentials)
                _fetch_data_from_scraper(scraper, start_date, db_path)
                st.session_state.pulled_data_status[f"{service}_{provider}_{account}"]  # noqa
    del st.session_state.pulled_data_from
    del st.session_state.pulling_data
    st.session_state.pulled_data_status.update(label="Data fetched", state="complete", expanded=True)


def _fetch_data_from_scraper(scraper: Scraper, start_date: datetime | str, db_path: str | None) -> None:
    """
    Fetch the data from the scraper and save it to the database

    Parameters
    ----------
    scraper : Scraper
        The scraper to use for fetching the data
    start_date : datetime | str
        The date from which to start fetching the data
    db_path : str
        The path to the database file. If None the database file will be created in the folder of fad package
        with the name 'data.db'

    Returns
    -------
    None
    """
    if scraper.requires_2fa:
        thread = Thread(target=scraper.pull_data_to_db, args=(start_date, db_path))
        thread.start()
        while thread.is_alive():
            if scraper.otp_code == "waiting for input":
                _two_fa_dialog(scraper, thread)
                st.stop()
            elif scraper.otp_code == "not required":
                break
            time.sleep(2)
    else:
        scraper.pull_data_to_db(start_date, db_path)
    _update_data_pulling_status(scraper)


@st.dialog('Two Factor Authentication')
def _two_fa_dialog(scraper: Scraper, thread: Thread):
    """
    Display a dialog for the user to enter the OTP code for the given provider. The dialog will stop the script
    until the user submits the code. If the user cancels the 2FA the tfa_code session state variable will be set to
    'cancel' and the script will rerun, otherwise the tfa_code session state variable will be set to the code
    entered by the user and the script will rerun as well.

    Parameters
    ----------
    scraper : Scraper
        The scraper for which to handle two-factor authentication

    Returns
    -------

    """
    st.write(f'The provider, {scraper.provider_name}, requires 2 factor authentication for fetching data.')
    st.write('Please enter the code you received.')
    code = st.text_input('Code', key=f'tfa_code_dialog_text_input')
    if st.button('Submit', key="two_fa_dialog_submit"):
        _handle_2fa_code(scraper, thread, code)
        st.rerun()
    if st.button('Cancel', key="two_fa_dialog_cancel"):
        _handle_2fa_code(scraper, thread, "cancel")
        st.rerun()


def _handle_2fa_code(scraper: Scraper, thread: Thread, code: str):
    if code is None or code == '':
        st.error('Please enter a valid code')
        st.stop()
    scraper.set_otp_code(code)
    thread.join()
    _update_data_pulling_status(scraper)


def _update_data_pulling_status(scraper: Scraper):
    name = f"{scraper.service_name}_{scraper.provider_name}_{scraper.account_name}"
    if not scraper.error:
        st.session_state.pulled_data_status[name] = st.success(
            f"Data fetched successfully from: {name.replace('_', ' - ')}",
            icon="✅"
        )
    else:
        st.session_state.pulled_data_status[name] = st.warning(
            f"Failed to fetch data from: {name.replace('_', ' - ')}. {scraper.error}",
            icon="⚠️"
        )


def get_latest_data_date(conn: SQLConnection) -> datetime.date:
    """
    Get the latest date in the database

    Parameters
    ----------
    conn : sqlite3.Connection
        The connection to the database

    Returns
    -------
    datetime.date:
        The latest date in the database
    """
    cc_table = Tables.CREDIT_CARD.value
    bank_table = Tables.BANK.value
    date_col_cc = CreditCardTableFields.DATE.value
    date_col_bank = BankTableFields.DATE.value

    query_cc = f'SELECT MAX({date_col_cc}) FROM {cc_table}'
    query_bank = f'SELECT MAX({date_col_bank}) FROM {bank_table}'
    try:
        latest_date_cc = conn.query(query_cc, ttl=0).iloc[0, 0]
        latest_date_bank = conn.query(query_bank, ttl=0).iloc[0, 0]
    except sqlalchemy.exc.OperationalError as e:
        if 'no such table' in str(e):
            return datetime.today() - timedelta(days=365)
        else:
            raise e

    latest_date_cc = datetime.strptime(latest_date_cc, '%Y-%m-%d')
    latest_date_bank = datetime.strptime(latest_date_bank, '%Y-%m-%d')
    latest_date = max(latest_date_cc, latest_date_bank)
    return latest_date


def update_db_table(conn: SQLConnection, table_name: str, edited_rows: pd.DataFrame) -> None:
    """
    Update the database table with the edited rows

    Parameters
    ----------
    conn : SQLConnection
        The connection to the database
    table_name : str
        The name of the table to update
    edited_rows : pd.DataFrame
        The edited rows

    Returns
    -------
    None
    """
    if edited_rows.empty:
        return
    match table_name:
        case Tables.CREDIT_CARD.value:
            id_col = CreditCardTableFields.ID.value
        case Tables.BANK.value:
            id_col = BankTableFields.ID.value
        case Tables.INSURANCE.value:
            raise NotImplementedError('Insurance table update is not implemented yet')
        case _:
            raise ValueError(f'Invalid table name: {table_name}')

    columns = edited_rows.columns.tolist()
    with conn.session as s:
        for i, row in edited_rows.iterrows():
            set_clause = ', '.join([f"{col}=:{col}" for col in columns])
            query = sqlalchemy.text(f"UPDATE {table_name} SET {set_clause} WHERE {id_col}=:id_col")
            params = {col: row[col] for col in columns}
            params['id_col'] = row[id_col]
            s.execute(query, params)
        s.commit()


def format_category_or_tag_strings(*args) -> tuple[str | None] | str | None:
    """
    format the category and tag to be title case

    Parameters
    ----------
    args: tuple[str | None]
        sequence of strings to format to title case

    Returns
    -------
    tuple
        the formatted category and tag
    """
    assert all(
        isinstance(arg, str) or arg is None or np.isnan(arg) for arg in args), 'all arguments should be strings'
    strings = tuple(arg.title() if isinstance(arg, str) and arg != '' else None for arg in args)
    if len(strings) == 1:
        return strings[0]
    return strings  # type: ignore


def update_tags_according_to_auto_tagger():
    """
    Update the tags table according to the auto tagger rules

    Returns
    -------
    None
    """
    # get the tags table
    conn = get_db_connection()
    assure_tags_table(conn)
    tags_df = get_table(conn, tags_table)
    cc_df = get_table(conn, credit_card_table)
    bank_df = get_table(conn, bank_table)

    # set the category and tag columns
    for _, row in tags_df.iterrows():
        category = row[tags_category_col]
        tag = row[tag_col]
        name = row[tags_name_col]
        service = row[tags_service_col]
        account = row[tags_account_number_col]

        cc_df.loc[(cc_df[cc_name_col] == name), cc_category_col] = category
        cc_df.loc[(cc_df[cc_name_col] == name), cc_tag_col] = tag
        bank_df.loc[(bank_df[bank_name_col] == name) & (
                bank_df[bank_account_number_col] == account), bank_category_col] = category
        bank_df.loc[
            (bank_df[bank_name_col] == name) & (bank_df[bank_account_number_col] == account), bank_tag_col] = tag

    # update the tables
    update_db_table(conn, credit_card_table, cc_df)
    update_db_table(conn, bank_table, bank_df)

    st.dataframe(cc_df)
    st.dataframe(bank_df)
