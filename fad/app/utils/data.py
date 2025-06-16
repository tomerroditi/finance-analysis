import os
import streamlit as st
import sqlalchemy
import pandas as pd
from sqlalchemy.sql import text

from streamlit.connections import SQLConnection
from fad import DB_PATH
from fad.app.naming_conventions import (
    CreditCardTableFields,
    Tables,
    BankTableFields,
    AutoTaggerTableFields,
    BudgetRulesTableFields,
)


tags_table = Tables.AUTO_TAGGER.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
tags_category_col = AutoTaggerTableFields.CATEGORY.value
tag_col = AutoTaggerTableFields.TAG.value
tags_name_col = AutoTaggerTableFields.NAME.value
tags_service_col = AutoTaggerTableFields.SERVICE.value
tags_account_number_col = AutoTaggerTableFields.ACCOUNT_NUMBER.value
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
cc_status_col = CreditCardTableFields.STATUS.value
cc_type_col = CreditCardTableFields.TYPE.value
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
bank_status_col = BankTableFields.STATUS.value
bank_type_col = BankTableFields.TYPE.value
br_id = BudgetRulesTableFields.ID.value
br_name = BudgetRulesTableFields.NAME.value
br_year = BudgetRulesTableFields.YEAR.value
br_month = BudgetRulesTableFields.MONTH.value
br_category = BudgetRulesTableFields.CATEGORY.value
br_tags = BudgetRulesTableFields.TAGS.value
br_amount = BudgetRulesTableFields.AMOUNT.value

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
            text(
                f'CREATE TABLE IF NOT EXISTS budget_rules ({br_id} INTEGER PRIMARY KEY, {br_name} TEXT, {br_amount} REAL, '
                f'{br_category} TEXT, {br_tags} TEXT, {br_year} INTEGER, {br_month} INTEGER);'
            )
        )
        s.commit()


def assure_transactions_table(conn: SQLConnection, table_name: str):
    """create the transactions table if it doesn't exist"""
    with conn.session as s:
        if table_name == Tables.CREDIT_CARD.value:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {credit_card_table} ({cc_id_col} INTEGER PRIMARY KEY, '
                     f'{cc_date_col} TEXT, {cc_amount_col} REAL, {cc_desc_col} TEXT, {cc_tag_col} TEXT, '
                     f'{cc_category_col} TEXT, {cc_provider_col} TEXT, {cc_account_name_col} TEXT, '
                     f'{cc_account_number_col} TEXT, {cc_status_col} TEXT, {cc_type_col} TEXT);'))
        elif table_name == Tables.BANK.value:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {bank_table} ({bank_id_col} INTEGER PRIMARY KEY, '
                     f'{bank_date_col} TEXT, {bank_amount_col} REAL, {bank_desc_col} TEXT, {bank_tag_col} TEXT, '
                     f'{bank_category_col} TEXT, {bank_provider_col} TEXT, {bank_account_name_col} TEXT, '
                     f'{bank_account_number_col} TEXT, {bank_status_col} TEXT, {bank_type_col} TEXT);'))
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

