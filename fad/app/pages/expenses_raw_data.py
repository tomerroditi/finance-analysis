"""
this page should display the database of the raw data of the expenses as an editable table.
the user should be able to:
- add new transactions
- edit existing transactions
- delete transactions
"""

import streamlit as st
import pandas as pd
import streamlit_pandas

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
create_data = {
    TransactionsTableFields.PROVIDER.value: 'multiselect',
    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
    TransactionsTableFields.DATE.value: 'multiselect',
    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
    TransactionsTableFields.CATEGORY.value: 'multiselect',
    TransactionsTableFields.TAG.value: 'multiselect',
    TransactionsTableFields.STATUS.value: 'multiselect',
    TransactionsTableFields.TYPE.value: 'multiselect',
}
ignored_columns = [TransactionsTableFields.ID.value]
data = st.selectbox('Select the data to edit:', [credit_card_table, bank_table])
with st.form(key='raw_data_transactions_editor_form'):
    if data == credit_card_table:
        widgets = streamlit_pandas.create_widgets(credit_card_data, create_data, ignore_columns=ignored_columns)
        widgets = sorted(widgets, key=lambda item: item[0])
        edited_data = st.data_editor(streamlit_pandas.filter_df(credit_card_data, widgets),
                                     key='cc_transactions_editor',
                                     column_order=columns_order, num_rows="fixed", hide_index=False)
        submit_button = st.form_submit_button(label='Save', on_click=DataUtils.update_db_table,
                                              args=(conn, credit_card_table, edited_data, columns_order))
    else:
        widgets = streamlit_pandas.create_widgets(bank_data, create_data, ignore_columns=ignored_columns)
        widgets = sorted(widgets, key=lambda item: item[0])
        edited_data = st.data_editor(streamlit_pandas.filter_df(bank_data, widgets),
                                     key='bank_transactions_editor',
                                     column_order=columns_order, num_rows="fixed", hide_index=False)
        submit_button = st.form_submit_button(label='Save', on_click=DataUtils.update_db_table,
                                              args=(conn, bank_table, edited_data, columns_order))
