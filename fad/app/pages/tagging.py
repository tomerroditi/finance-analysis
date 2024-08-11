import time

import streamlit as st
import yaml
import numpy as np
import pandas as pd

from streamlit.connections import SQLConnection
from sqlalchemy.sql import text
from streamlit_tags import st_tags
from fad import CATEGORIES_PATH
from fad.app.utils import DataUtils, PandasFilterWidgets
from fad.naming_conventions import (TagsTableFields,
                                    Tables,
                                    CreditCardTableFields,
                                    BankTableFields,
                                    TransactionsTableFields)

tags_table = Tables.TAGS.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
category_col = TagsTableFields.CATEGORY.value
tag_col = TagsTableFields.TAG.value
name_col = TagsTableFields.NAME.value
service_col = TagsTableFields.SERVICE.value
account_number_col = TagsTableFields.ACCOUNT_NUMBER.value
cc_desc_col = CreditCardTableFields.DESCRIPTION.value
cc_tag_col = CreditCardTableFields.TAG.value
cc_category_col = CreditCardTableFields.CATEGORY.value
cc_name_col = CreditCardTableFields.DESCRIPTION.value
cc_id_col = CreditCardTableFields.ID.value
bank_desc_col = BankTableFields.DESCRIPTION.value
bank_tag_col = BankTableFields.TAG.value
bank_category_col = BankTableFields.CATEGORY.value
bank_name_col = BankTableFields.DESCRIPTION.value
bank_id_col = BankTableFields.ID.value
bank_account_number_col = BankTableFields.ACCOUNT_NUMBER.value


# TODO: refactor this module by moving all its functions into the utils module
# TODO: when deleting tags/categories make sure to delete them from the tags and credit card tables
# TODO: add a feature that enables one to split a transaction into multiple transactions of different amounts and tags
# TODO: add a feature to mark if you want to update all tagged rows with the auto tagger new value or only future rows
#   when editing the tags in the auto tagger
# TODO: make it impossible to delete the Other, Salaries, Savings, and Investments categories
# TODO: make it impossible to delete the Other: No tag tag
# TODO: add a feature to shift the tags of a category to another category and update the tagged data accordingly
def edit_categories_and_tags(categories_and_tags: dict, yaml_path: str, conn: SQLConnection):
    """
    Display the categories and tags and allow editing them

    Parameters
    ----------
    categories_and_tags: dict
        a dictionary of categories and their tags
    yaml_path: str
        the path to the yaml file that contains the categories and tags
    conn: SQLConnection
        the connection to the database

    Returns
    -------

    """
    # Initialize session state for each category before the loop
    for category in categories_and_tags.keys():
        if f'confirm_delete_{category}' not in st.session_state:
            st.session_state[f'confirm_delete_{category}'] = False

    # Iterate over a copy of the dictionary's items and display the categories and tags and allow editing
    for category, tags in list(categories_and_tags.items()):
        st.subheader(category, divider="gray")
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            categories_and_tags[category] = new_tags
            # save changes and rerun to update the UI
            update_yaml_and_rerun(categories_and_tags, yaml_path)

        # delete category
        delete_button = st.button(f'Delete {category}', key=f'my_{category}_delete')
        if delete_button:
            st.session_state[f'confirm_delete_{category}'] = True

        # confirm deletion
        if st.session_state[f'confirm_delete_{category}']:
            confirm_button = st.button('Confirm Delete', key=f'confirm_{category}_delete')
            cancel_button = st.button('Cancel', key=f'cancel_{category}_delete')

            # delete and update database
            if confirm_button:
                del categories_and_tags[category]
                data_to_delete = conn.query(f'SELECT {name_col} FROM {tags_table} WHERE {category_col}={category_col};',
                                            ttl=0)
                with conn.session as s:
                    for i, row in data_to_delete.iterrows():
                        s.execute(text(f"UPDATE {tags_table} SET {category_col}='', {tag_col}='' "
                                       f"WHERE {name_col}={row[name_col]};"))
                    s.commit()
                del st.session_state[f'confirm_delete_{category}']
                update_yaml_and_rerun(categories_and_tags, yaml_path)

            # cancel deletion
            if cancel_button:
                st.session_state[f'confirm_delete_{category}'] = False
                st.rerun()

    # add new categories
    st.subheader('Add a new Category', divider="gray")
    new_category = st.text_input('New Category Name', key='new_category')
    if st.button('Add Category') and new_category != '':
        categories_and_tags[new_category] = []
        update_yaml_and_rerun(categories_and_tags, yaml_path)


def update_yaml_and_rerun(categories_and_tags, yaml_path):
    """update the yaml file and rerun the streamlit app"""
    # sort the categories and tags by alphabetical order
    categories_and_tags = {category: sorted(tags) for category, tags in categories_and_tags.items()}
    categories_and_tags = dict(sorted(categories_and_tags.items()))
    st.session_state["categories_and_tags"] = categories_and_tags
    with open(yaml_path, 'w') as file:
        yaml.dump(categories_and_tags, file)
    st.rerun()


def update_raw_data_tags(conn: SQLConnection):
    """update the tags of the raw data in the credit card and bank tables of deleted categories and tags"""
    tags_table_data = conn.query(f'SELECT * FROM {tags_table};', ttl=0)
    credit_card_data = conn.query(f'SELECT * FROM {credit_card_table};', ttl=0)
    bank_data = conn.query(f'SELECT * FROM {bank_table};', ttl=0)

    cc_changed_locs = []
    bank_changed_locs = []
    tags_table_data = tags_table_data.dropna(subset=[category_col, tag_col])
    for i, row in tags_table_data.iterrows():
        cc_name_cond = credit_card_data[cc_name_col] == row[name_col]
        cc_category_nan_cond = credit_card_data[cc_category_col].isna()
        credit_card_data.loc[cc_name_cond & cc_category_nan_cond, cc_category_col] = row[category_col]
        credit_card_data.loc[cc_name_cond & cc_category_nan_cond, cc_tag_col] = row[tag_col]
        cc_changed_locs.append((cc_name_cond & cc_category_nan_cond).to_numpy())

        bank_name_cond = bank_data[bank_name_col] == row[name_col]
        bank_category_nan_cond = bank_data[bank_category_col].isna()
        bank_data.loc[bank_name_cond & bank_category_nan_cond, bank_category_col] = row[category_col]
        bank_data.loc[bank_name_cond & bank_category_nan_cond, bank_tag_col] = row[tag_col]
        bank_changed_locs.append((bank_name_cond & bank_category_nan_cond).to_numpy())

    cc_changed_locs = np.logical_or.reduce(np.stack(cc_changed_locs, axis=1), axis=1)
    bank_changed_locs = np.logical_or.reduce(np.stack(bank_changed_locs, axis=1), axis=1)
    DataUtils.update_db_table(conn, credit_card_table,
                              credit_card_data.loc[cc_changed_locs, [cc_id_col, cc_category_col, cc_tag_col]])
    DataUtils.update_db_table(conn, bank_table,
                              bank_data.loc[bank_changed_locs, [bank_id_col, bank_category_col, bank_tag_col]])


def assure_tags_table(conn: SQLConnection):
    """create the tags table if it doesn't exist"""
    with conn.session as s:
        s.execute(text(f'CREATE TABLE IF NOT EXISTS {tags_table} ({name_col} TEXT PRIMARY KEY, {category_col}'
                       f' TEXT, {tag_col} TEXT, {service_col} TEXT, {account_number_col} TEXT);'))
        s.commit()


def pull_new_cc_names(conn):
    """pull new credit card transactions names from the credit card table and insert them into the tags table"""
    current_cc_names = conn.query(
        f"SELECT {name_col} FROM {tags_table} WHERE {service_col}='credit_card';", ttl=0
    )
    cc_names = conn.query(f"SELECT {cc_desc_col} FROM {credit_card_table};", ttl=0)
    new_cc_names = cc_names.loc[~cc_names[cc_desc_col].isin(current_cc_names[name_col]), cc_desc_col].unique()
    with conn.session as s:
        for name in new_cc_names:
            s.execute(text(f'INSERT INTO {tags_table} ({name_col}, {service_col}) VALUES (:curr_name, "credit_card");'),
                      {'curr_name': name})
        s.commit()


def pull_new_bank_names(conn):
    """pull new bank transactions names from the bank table and insert them into the tags table"""
    current_banks_names = conn.query(
        f"SELECT {name_col}, {account_number_col} FROM {tags_table} WHERE {service_col} = 'bank';", ttl=0
    )
    bank_names = conn.query(f"SELECT {bank_desc_col}, {bank_account_number_col} FROM {bank_table};", ttl=0)
    new_bank_names = bank_names.loc[~bank_names[bank_desc_col].isin(current_banks_names[name_col]) &
                                    ~bank_names[bank_account_number_col].isin(current_banks_names[account_number_col]),
                                    [bank_desc_col, bank_account_number_col]].drop_duplicates()
    with conn.session as s:
        for i, row in new_bank_names.iterrows():
            s.execute(text(f'INSERT INTO {tags_table} ({name_col}, {account_number_col}, {service_col})'
                           f' VALUES (:curr_name, :curr_account_number, "bank");'),
                      {'curr_name': row[bank_desc_col], 'curr_account_number': row[bank_account_number_col]})
        s.commit()


def tag_new_cc_data(conn, categories_and_tags):
    """tag new credit card data"""

    df_tags = conn.query(f"""
        SELECT * FROM {tags_table}
        WHERE ({category_col} IS NULL OR {tag_col} IS NULL) AND {service_col} = 'credit_card';
        """,
        ttl=0
    )
    if df_tags.empty:
        st.write("No data to tag")
        return

    # editable table to tag the data
    categories = list(categories_and_tags.keys())
    tags = [f'{category}: {tag}' for category in categories for tag in categories_and_tags[category]]
    df_tags['new tag'] = ''
    tags_col = st.column_config.SelectboxColumn('new tag', options=tags)
    edited_df_tags = st.data_editor(df_tags[[name_col, 'new tag']], hide_index=True, width=800,
                                    column_config={'new tag': tags_col})

    # save the edited data
    if st.button('Save', key='save_cc_tagged_data'):
        edited_df_tags = edited_df_tags.loc[edited_df_tags['new tag'] != '']
        if not edited_df_tags.empty:
            edited_df_tags[category_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[0])
            edited_df_tags[tag_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[1])
            edited_df_tags = edited_df_tags.drop('new tag', axis=1)
            with conn.session as s:
                for i, row in edited_df_tags.iterrows():
                    query = text(f"""
                            UPDATE {tags_table}
                            SET {category_col} = :category_val, {tag_col} = :tag_val
                            WHERE {name_col} = :name_val
                        """)
                    params = {
                        'category_val': row[category_col],
                        'tag_val': row[tag_col],
                        'name_val': row[name_col]
                    }
                    s.execute(query, params)
                s.commit()
        st.rerun()


def tag_new_bank_data(conn, categories_and_tags):
    """tag new bank data"""
    df_tags = conn.query(f"""
        SELECT * FROM {tags_table}
        WHERE ({category_col} IS NULL OR {tag_col} IS NULL)
        AND {service_col} = 'bank';
        """,
        ttl=0)
    if df_tags.empty:
        st.write("No data to tag")
        return

    # editable table to tag the data
    categories = list(categories_and_tags.keys())
    tags = [f'{category}: {tag}' for category in categories for tag in categories_and_tags[category]]
    df_tags['new tag'] = ''
    tags_col = st.column_config.SelectboxColumn('new tag', options=tags)
    edited_df_tags = st.data_editor(df_tags[[name_col, account_number_col, 'new tag']], hide_index=True, width=800,
                                    column_config={'new tag': tags_col})

    # save the edited data
    if st.button('Save', key='save_bank_tagged_data'):
        edited_df_tags = edited_df_tags.loc[edited_df_tags['new tag'] != '']
        if not edited_df_tags.empty:
            edited_df_tags[category_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[0])
            edited_df_tags[tag_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[1])
            edited_df_tags = edited_df_tags.drop('new tag', axis=1)
            with conn.session as s:
                for i, row in edited_df_tags.iterrows():
                    query = text(f"""
                            UPDATE {tags_table}
                            SET {category_col} = :category_val, {tag_col} = :tag_val
                            WHERE {name_col} = :name_val AND {account_number_col} = :account_number_val
                        """)
                    params = {
                        'category_val': row[category_col],
                        'tag_val': row[tag_col],
                        'name_val': row[name_col],
                        'account_number_val': row[account_number_col]
                    }
                    s.execute(query, params)
                s.commit()
        st.rerun()


def edit_cc_tagged_data(conn):
    """edit tagged credit card data within the tags table"""
    tagged_data = conn.query(
        f"SELECT * FROM {tags_table} "
        f"WHERE {category_col}!='' "
        f"AND {tag_col}!='' "
        f"AND {service_col} = 'credit_card';",
        ttl=0)
    if tagged_data.empty:
        st.write("No data to edit")
        return

    # editable table to edit the tagged data
    edited_tagged_data = st.data_editor(tagged_data[[name_col, category_col, tag_col]],
                                        hide_index=True, width=800, key='edit_cc_tagged_data')
    if st.button('Save', key='save_edited_cc_tagged_data'):
        # keep only the modified rows
        edited_tagged_data = edited_tagged_data[(edited_tagged_data[category_col] != tagged_data[category_col]) |
                                                (edited_tagged_data[tag_col] != tagged_data[tag_col])]
        # save the edited data to the database
        with conn.session as s:
            for i, row in edited_tagged_data.iterrows():
                params = {
                    name_col: row[name_col],
                    category_col: row[category_col] if row[category_col] != '' else None,
                    tag_col: row[tag_col] if row[tag_col] != '' else None
                }
                s.execute(text(f'UPDATE {tags_table} SET {category_col}=:{category_col}, {tag_col}=:{tag_col}'
                               f' WHERE {name_col}=:{name_col};'),
                          params)
            s.commit()
        st.rerun()


def edit_bank_tagged_data(conn):
    """edit tagged bank data within the tags table"""
    tagged_data = conn.query(
        f"SELECT * FROM {tags_table} "
        f"WHERE {category_col}!='' "
        f"AND {tag_col}!='' "
        f"AND {service_col} = 'bank';",
        ttl=0)
    if tagged_data.empty:
        st.write("No data to edit")
        return

    # editable table to edit the tagged data
    edited_tagged_data = st.data_editor(tagged_data[[name_col, account_number_col, category_col, tag_col]],
                                        hide_index=True, width=800, key='edit_bank_tagged_data')
    if st.button('Save', key='save_edited_bank_tagged_data'):
        # keep only the modified rows
        edited_tagged_data = edited_tagged_data[(edited_tagged_data[category_col] != tagged_data[category_col]) |
                                                (edited_tagged_data[tag_col] != tagged_data[tag_col])]
        # save the edited data to the database
        with conn.session as s:
            for i, row in edited_tagged_data.iterrows():
                params = {
                    name_col: row[name_col],
                    account_number_col: row[account_number_col],
                    category_col: row[category_col] if row[category_col] != '' else None,
                    tag_col: row[tag_col] if row[tag_col] != '' else None
                }
                s.execute(text(f'UPDATE {tags_table} SET {category_col}=:{category_col}, {tag_col}=:{tag_col}'
                               f' WHERE {name_col}=:{name_col} AND {account_number_col}=:{account_number_col};'),
                          params)
            s.commit()
        st.rerun()


conn = DataUtils.get_db_connection()
categories_and_tags = DataUtils.get_categories_and_tags()
tab_tags, tab_auto_tagger, tab_raw_data = st.tabs(["Categories & Tags", "Automatic Tagger", "Raw Data"])

with tab_tags:
    st.caption("<p style='font-size:20px; color: black;'>"
               "Add, edit or delete categories and tags here.<br>"
               "Note that deleted tags will be removed from the tagged data as well."
               "</p>",
               unsafe_allow_html=True)
    edit_categories_and_tags(categories_and_tags, CATEGORIES_PATH, conn)
    update_raw_data_tags(conn)

with tab_auto_tagger:
    st.caption("<p style='font-size:20px; color: black;'>"
               "The automatic tagger will tag new data according to the rules you set here making the tagging process "
               "less time consuming."
               "</p>",
               unsafe_allow_html=True)
    assure_tags_table(conn)
    pull_new_cc_names(conn)
    pull_new_bank_names(conn)
    cc_tab, bank_tab = st.tabs(["Credit Card", "Bank"])

    with cc_tab:
        tag_new_cc_data(conn, categories_and_tags)
        edit_cc_tagged_data(conn)

    with bank_tab:
        tag_new_bank_data(conn, categories_and_tags)
        edit_bank_tagged_data(conn)

with tab_raw_data:
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

    table_type = st.selectbox(
        'Select data table to edit:',
        [credit_card_table.replace('_', ' '), bank_table.replace('_', ' ')],
        key="tagging_raw_data_table_type"
    )
    table_type = table_type.replace(' ', '_')
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
                df_data, key=f'{prefix}transactions_editor', column_order=columns_order, num_rows="fixed",
                hide_index=False
            )
            edited_data = edited_data.merge(df_data, how='outer', indicator=True)
            edited_data = edited_data[edited_data['_merge'] == 'left_only'].drop('_merge', axis=1)

            submit_button = st.form_submit_button(label='Save')
            if submit_button:
                DataUtils.update_db_table(conn, table_type, edited_data)
                st.success("Data saved successfully")
