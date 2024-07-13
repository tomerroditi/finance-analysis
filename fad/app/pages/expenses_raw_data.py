"""
this page should display the database of the raw data of the expenses as an editable table.
the user should be able to:
- add new transactions
- edit existing transactions
- delete transactions
"""

import streamlit as st
import pandas as pd

from sqlalchemy.exc import OperationalError
from fad.app.utils import DataUtils
from fad.naming_conventions import Tables, TransactionsTableFields

# TODO: add a provider column to the credit card table and the bank table
conn = DataUtils.get_db_connection()

# get the data from the database
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value

credit_card_data = DataUtils.get_table(conn, credit_card_table)
bank_data = DataUtils.get_table(conn, bank_table)

columns_order = [TransactionsTableFields.PROVIDER.value,
                 TransactionsTableFields.ACCOUNT_NAME.value,
                 TransactionsTableFields.ACCOUNT_NUMBER.value,
                 TransactionsTableFields.DATE.value,
                 TransactionsTableFields.DESCRIPTION.value,
                 TransactionsTableFields.AMOUNT.value,
                 TransactionsTableFields.CATEGORY.value,
                 TransactionsTableFields.TAG.value,
                 TransactionsTableFields.ID.value,
                 TransactionsTableFields.STATUS.value,
                 TransactionsTableFields.TYPE.value]

# display the data
st.subheader('Credit Card Transactions', divider="gray")
with st.form(key='credit_card_transactions_editor_form'):
    edited_data_cc = st.data_editor(credit_card_data, key='credit_card_transactions_editor', column_order=columns_order,
                                    num_rows="dynamic", hide_index=True)
    submit_button_cc = st.form_submit_button(label='Submit', on_click=DataUtils.update_db_table,
                                             args=(conn, credit_card_table, edited_data_cc, columns_order))


st.subheader('Bank Transactions', divider="gray")
with st.form(key='bank_transactions_editor_form'):
    edited_data_bank = st.data_editor(bank_data, key='bank_transactions_editor', column_order=columns_order,
                                      num_rows="dynamic", hide_index=True)
    submit_button_bank = st.form_submit_button(label='Submit', on_click=DataUtils.update_db_table,
                                               args=(conn, bank_table, edited_data_bank, columns_order))
