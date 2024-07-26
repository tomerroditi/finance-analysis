"""
this page should display the database of the raw data of the expenses as an editable table.
the user should be able to:
- add new transactions
- edit existing transactions
- delete transactions
"""

import streamlit as st

from fad.app.utils import DataUtils, PandasFilterWidgets
from fad.naming_conventions import Tables, TransactionsTableFields

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
widgets_map = {
    TransactionsTableFields.AMOUNT.value: 'number_range',
    TransactionsTableFields.DATE.value: 'date_range',
    TransactionsTableFields.PROVIDER.value: 'multiselect',
    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
    TransactionsTableFields.CATEGORY.value: 'multiselect',
    TransactionsTableFields.TAG.value: 'multiselect',
    TransactionsTableFields.STATUS.value: 'multiselect',
    TransactionsTableFields.TYPE.value: 'multiselect',
}

ignored_columns = [TransactionsTableFields.ID.value]
table_type = st.selectbox(
    'Select data table to edit:', [credit_card_table.replace('_', ' '), bank_table.replace('_', ' ')]
)
# select the desired table you want to edit
if table_type == credit_card_table:
    df_data = credit_card_data
    prefix = 'cc_'
else:
    df_data = bank_data
    prefix = 'bank_'

widget_col, data_col = st.columns([0.2, 0.8])

# filter the data according to the user's input
with widget_col:
    df_filter = PandasFilterWidgets(df_data, widgets_map, keys_prefix=prefix)
    df_data = df_filter.filter_df()

# display the data and bulk edit it
with data_col:
    with st.form(key='raw_data_transactions_editor_form', border=False):
        edited_data = st.data_editor(
            df_data, key=f'{prefix}transactions_editor', column_order=columns_order, num_rows="fixed", hide_index=False
        )
        submit_button = st.form_submit_button(
            label='Save', on_click=DataUtils.update_db_table, args=(conn, table_type, edited_data, columns_order)
        )
