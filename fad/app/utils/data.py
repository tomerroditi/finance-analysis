import os
import streamlit as st
import yaml
import sqlite3
import sqlalchemy
import pandas as pd
from sqlalchemy.sql import text
from threading import Thread
from copy import deepcopy

from streamlit.connections import SQLConnection
from datetime import datetime, timedelta
from fad.scraper import get_scraper, Scraper
from fad import CATEGORIES_PATH, DB_PATH
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
        if not os.path.exists(DB_PATH):
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(DB_PATH, 'w'):
                pass

        st.session_state['conn'] = st.connection('data', 'sql')
        assure_tags_table(st.session_state['conn'])
        assure_budget_rules_table(st.session_state['conn'])
        assure_transactions_table(st.session_state['conn'], Tables.CREDIT_CARD.value)
        assure_transactions_table(st.session_state['conn'], Tables.BANK.value)
    return st.session_state['conn']


def assure_tags_table(conn: SQLConnection):
    """create the tags table if it doesn't exist"""
    with conn.session as s:
        s.execute(
            text(f'CREATE TABLE IF NOT EXISTS {tags_table} ({tags_name_col} TEXT PRIMARY KEY, {tags_category_col}'
                 f' TEXT, {tag_col} TEXT, {tags_service_col} TEXT, {tags_account_number_col} TEXT);'))
        s.commit()


def assure_budget_rules_table(conn: SQLConnection):
    """create the budget table if it doesn't exist"""
    with conn.session as s:
        s.execute(
            text(f'CREATE TABLE IF NOT EXISTS budget_rules (id INTEGER PRIMARY KEY, name TEXT, amount REAL, '
                 f'category TEXT, tag TEXT, year INTEGER, month INTEGER);'))
        s.commit()

def assure_transactions_table(conn: SQLConnection, table_name: str):
    """create the transactions table if it doesn't exist"""
    with conn.session as s:
        if table_name == Tables.CREDIT_CARD.value:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {credit_card_table} ({cc_id_col} INTEGER PRIMARY KEY, '
                     f'{cc_date_col} TEXT, {cc_amount_col} REAL, {cc_desc_col} TEXT, {cc_tag_col} TEXT, '
                     f'{cc_category_col} TEXT, {cc_provider_col} TEXT, {cc_account_name_col} TEXT, '
                     f'{cc_account_number_col} TEXT);'))
        elif table_name == Tables.BANK.value:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {bank_table} ({bank_id_col} INTEGER PRIMARY KEY, '
                     f'{bank_date_col} TEXT, {bank_amount_col} REAL, {bank_desc_col} TEXT, {bank_tag_col} TEXT, '
                     f'{bank_category_col} TEXT, {bank_provider_col} TEXT, {bank_account_name_col} TEXT, '
                     f'{bank_account_number_col} TEXT);'))
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
    if table_name == tags_table:
        assure_tags_table(conn)
    elif table_name == Tables.BUDGET_RULES.value:
        assure_budget_rules_table(conn)
    elif table_name in [Tables.CREDIT_CARD.value, Tables.BANK.value]:
        assure_transactions_table(conn, table_name)

    try:
        return conn.query(f'SELECT * FROM {table_name};', ttl=0)
    except sqlalchemy.exc.OperationalError:
        return pd.DataFrame()


def get_categories_and_tags(copy: bool = False) -> dict:
    """
    Get the categories and tags from the yaml file

    Returns
    -------
    dict
        The categories and tags dictionary
    """
    if 'categories_and_tags' not in st.session_state:
        if not os.path.exists(CATEGORIES_PATH):
            os.makedirs(os.path.dirname(CATEGORIES_PATH), exist_ok=True)
            with open(CATEGORIES_PATH, 'w') as file:
                yaml.dump({}, file)

        with open(CATEGORIES_PATH, 'r') as file:
            st.session_state['categories_and_tags'] = yaml.load(file, Loader=yaml.FullLoader)

    if copy:
        return deepcopy(st.session_state['categories_and_tags'])
    return st.session_state['categories_and_tags']


def pull_data_from_all_scrapers_to_db(start_date: datetime | str, credentials: dict, db_path: str | None = None) -> None:
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
    if "current_pulled_resources" not in st.session_state:  # for 2fa dialog
        st.session_state.current_pulled_resources = []

    for service, providers in credentials.items():
        for provider, accounts in providers.items():
            for account, credentials in accounts.items():
                name = f"{service}_{provider}_{account}".replace('_', ' - ')
                if name in st.session_state.current_pulled_resources:
                    continue
                scraper = get_scraper(service, provider, account, credentials)
                pull_data_from_scraper_to_db(scraper, start_date, db_path)
    del st.session_state.current_pulled_resources


def pull_data_from_scraper_to_db(scraper: Scraper, start_date: datetime | str, db_path: str | None) -> None:
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
        _pull_data_from_2fa_scraper_to_db(scraper, start_date, db_path)
    else:
        scraper.pull_data_to_db(start_date, db_path)
        _finalize_scraper_session_scraping(scraper)


def _pull_data_from_2fa_scraper_to_db(scraper: Scraper, start_date: datetime | str, db_path: str | None) -> None:
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
    thread = Thread(target=scraper.pull_data_to_db, args=(start_date, db_path))
    thread.start()
    while thread.is_alive():
        if scraper.otp_code == "waiting for input":
            _two_fa_dialog(scraper, thread)
            st.stop()
        elif scraper.otp_code == "not required":
            thread.join()
            _finalize_scraper_session_scraping(scraper)
            break


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
    st.write("Code submitted. Fetching data, please wait...")
    scraper.set_otp_code(code)
    thread.join()
    _finalize_scraper_session_scraping(scraper)


def _finalize_scraper_session_scraping(scraper: Scraper):
    name = f"{scraper.service_name}_{scraper.provider_name}_{scraper.account_name}".replace('_', ' - ')
    st.session_state.current_pulled_resources.append(name)
    if not scraper.error:
        st.session_state.data_pulling_status["success"][name] = f"{name} - Data fetched successfully: {datetime.now()}"
    else:
        st.session_state.data_pulling_status["failed"][name] =\
            f"{name} - Data fetching failed: {datetime.now()}. Error: {scraper.error}"


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

    latest_date_cc = conn.query(query_cc, ttl=0).iloc[0, 0]
    latest_date_bank = conn.query(query_bank, ttl=0).iloc[0, 0]

    if latest_date_cc is None:
        latest_date_cc = datetime.today() - timedelta(days=365)
    else:
        latest_date_cc = datetime.strptime(latest_date_cc, '%Y-%m-%d')

    if latest_date_bank is None:
        latest_date_bank = datetime.today() - timedelta(days=365)
    else:
        latest_date_bank = datetime.strptime(latest_date_bank, '%Y-%m-%d')

    latest_date = min(latest_date_cc, latest_date_bank)
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


def format_category_or_tag_strings(*args) -> None | str | tuple[str | None, ...]:
    """
    Format the given strings to title case and return them as a tuple. if a string is empty or None it will be returned
    as None, if a string is uppercase it will be returned as is. in case ';' is in the string an error will be raised
    by streamlit and the script will stop.

    Parameters
    ----------
    args : str
        The strings to format

    Returns
    -------
    None | str | tuple[str | None, ...]
        The formatted strings. If only one string is given it will be returned as a string, otherwise as a tuple of
        strings.
    """
    formated_strings = []
    for arg in args:
        if pd.isnull(arg) or arg == '':
            formated_strings.append(None)
        elif isinstance(arg, str):
            if ';' in arg:
                st.error(f'categories and tags must not contain ";". please rename: {arg}')
                st.stop()
            if arg.isupper():  # all caps should be kept as is (e.g. 'ATM')
                arg = arg
            else:
                arg = ' '.join([word.capitalize() for word in arg.split()])
            arg = arg.strip()
            formated_strings.append(arg)
        else:
            raise ValueError('all arguments should be strings or null')
    if len(formated_strings) == 1:
        return formated_strings[0]
    return tuple(formated_strings)


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
