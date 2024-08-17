import streamlit as st
import yaml
import pandas as pd
import numpy as np

from typing import Literal
from streamlit.connections import SQLConnection
from sqlalchemy.sql import text
from streamlit_tags import st_tags
from fad import CATEGORIES_PATH
from fad.app.utils import DataUtils, PandasFilterWidgets
from fad.naming_conventions import (TagsTableFields,
                                    Tables,
                                    Services,
                                    CreditCardTableFields,
                                    BankTableFields,
                                    TransactionsTableFields,
                                    NonExpensesCategories)

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
# TODO: add a feature that enables one to split a transaction into multiple transactions of different amounts and tags
# TODO: add a feature to mark if you want to update all tagged rows with the auto tagger new value or only future rows
#   when editing the tags in the auto tagger
# TODO: make it impossible to delete the Other: No tag tag
def edit_categories_and_tags(categories_and_tags: dict[str: list[str]], yaml_path: str, conn: SQLConnection):
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
    add_cat_col, reallocate_tags_col, _ = st.columns([0.2, 0.2, 0.6])
    # add new categories
    with add_cat_col:
        st.button('New Category', key='add_new_category', on_click=add_new_category,
                  args=(categories_and_tags, yaml_path))

    # reallocate tags
    with reallocate_tags_col:
        st.button('Reallocate Tags', key='reallocate_tags', on_click=reallocate_tags,
                  args=(categories_and_tags, conn, yaml_path))

    # Iterate over a copy of the dictionary's items and display the categories and tags and allow editing
    for category, tags in list(categories_and_tags.items()):
        st.subheader(category, divider="gray")
        if category == "Ignore":
            st.write("Transactions that you don't want to consider in the analysis. For example credit card bills in "
                     "you bank account (which are already accounted for in the credit card transactions tracking), "
                     "internal transfers, etc.")
        if category == "Salary":
            st.write("Transactions that are your salary income. we advise using the employer's name as the tag.")
        if category == "Other Income":
            st.write("Transactions that are income other than your salary. For example, rental income, dividends, "
                     "refunds, etc.")
        if category == "Investments":
            st.write("Transactions for investments you made. For example, depositing money into some fund, buying "
                     "stocks, real estate, etc.")
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            new_tags = [format_category_or_tag_strings(tag) for tag in new_tags]
            categories_and_tags[category] = new_tags
            # save changes and rerun to update the UI
            update_yaml_and_rerun(categories_and_tags, yaml_path)

        # delete category
        disable = True if category in [e.value for e in NonExpensesCategories] else False
        st.button(f'Delete {category}', key=f'my_{category}_delete', disabled=disable, on_click=delete_category,
                  args=(categories_and_tags, category, conn, yaml_path))


@st.dialog('Add New Category')
def add_new_category(categories_and_tags: dict[str: list[str]], yaml_path: str):
    existing_categories = [k.lower() for k in categories_and_tags.keys()]
    new_category = st.text_input('New Category Name', key='new_category')

    if st.button('Cancel'):
        st.rerun()

    if st.button('Continue') and new_category != '' and new_category is not None:
        if new_category.lower() in existing_categories:
            st.warning(f'The category "{new_category}" already exists. Please choose a different name.')
            st.stop()
        categories_and_tags[format_category_or_tag_strings(new_category)] = []
        update_yaml_and_rerun(categories_and_tags, yaml_path)


@st.dialog('Reallocate Tags')
def reallocate_tags(categories_and_tags: dict[str: list[str]], conn: SQLConnection, yaml_path: str):
    all_categories = list(categories_and_tags.keys())
    old_category = st.selectbox('Select current category', all_categories, index=None,
                                key='old_category')
    tags_to_select = categories_and_tags[old_category] if old_category is not None else []
    tags_to_reallocate = st.multiselect('Select tags to reallocate', tags_to_select, key='reallocate_tags')
    if old_category is None:
        st.stop()

    all_categories.remove(old_category)
    new_category = st.selectbox('Select new category', all_categories, key='new_category', index=None)
    if old_category is not None and new_category is not None and tags_to_reallocate:
        if st.button('Continue', key='continue_reallocate_tags'):
            # update the tags in the database
            for table in [tags_table, credit_card_table, bank_table]:
                match table:
                    case Tables.TAGS.value:
                        curr_tag_col = tag_col
                        curr_category_col = category_col
                    case Tables.CREDIT_CARD.value:
                        curr_tag_col = cc_tag_col
                        curr_category_col = cc_category_col
                    case Tables.BANK.value:
                        curr_tag_col = bank_tag_col
                        curr_category_col = bank_category_col
                    case _:
                        raise ValueError(f"Invalid table name: {table}")
                with (conn.session as s):
                    for tag in tags_to_reallocate:
                        query = text(f'UPDATE {table} SET {curr_category_col}=:new_category WHERE {curr_tag_col}=:tag AND '
                                     f'{curr_category_col}=:old_category;')
                        s.execute(query, {'new_category': new_category, 'tag': tag,
                                          'old_category': old_category})
                        s.commit()

            categories_and_tags[new_category].extend(tags_to_reallocate)
            _ = [categories_and_tags[old_category].remove(tag) for tag in tags_to_reallocate]
            update_yaml_and_rerun(categories_and_tags, yaml_path)


@st.dialog('Confirm Deletion')
def delete_category(categories_and_tags: dict[str: list[str]], category: str, conn: SQLConnection, yaml_path: str):
    st.write(f'Are you sure you want to delete the "{category}" category?')
    st.write('Deleting a category deletes it from the auto tagger rules as well.')
    delete_tags_of_logged_data = st.checkbox('Delete tags of logged data', key=f'delete_tags_of_logged_data')
    confirm_button = st.button('Continue', key=f'continue_delete_category')
    cancel_button = st.button('Cancel', key=f'cancel_delete_category')

    if confirm_button:
        data_to_delete = conn.query(f'SELECT {name_col} FROM {tags_table} WHERE {category_col}=:category',
                                    params={'category': category}, ttl=0)

        with conn.session as s:
            for i, row in data_to_delete.iterrows():
                query = text(f"UPDATE {tags_table} SET {category_col}=Null, {tag_col}=Null WHERE {name_col}=:name")
                s.execute(query, {'name': row[name_col]})
                s.commit()

        if delete_tags_of_logged_data:
            update_raw_data_deleted_category(conn, category)

        del categories_and_tags[category]
        update_yaml_and_rerun(categories_and_tags, yaml_path)

    if cancel_button:
        st.rerun()


def update_raw_data_deleted_category(conn: SQLConnection, category: str) -> None:
    """
    update the tags, to Null, of the raw data in the credit card and bank tables of deleted categories

    Parameters
    ----------
    conn: SQLConnection
        the connection to the database
    category: str
        the category to delete

    Returns
    -------
    None
    """
    for table in [credit_card_table, bank_table]:
        match table:
            case Tables.CREDIT_CARD.value:
                curr_tag_col = cc_tag_col
                curr_category_col = cc_category_col
            case Tables.BANK.value:
                curr_tag_col = bank_tag_col
                curr_category_col = bank_category_col
            case _:
                raise ValueError(f"Invalid table name: {table}")
        with conn.session as s:
            query = text(f"UPDATE {table} SET {curr_category_col}=Null, {curr_tag_col}=Null "
                         f"WHERE {curr_category_col}=:category")
            s.execute(query, {'category': category})
            s.commit()


def update_yaml_and_rerun(categories_and_tags: dict[str: list[str]], yaml_path: str) -> None:
    """
    update the yaml file and rerun the streamlit app

    Parameters
    ----------
    categories_and_tags: dict
        a dictionary of categories and their tags
    yaml_path: str
        the path to the yaml file that contains the categories and tags

    Returns
    -------
    None
    """
    # sort the categories and tags by alphabetical order
    categories_and_tags = {category: sorted(list(set(tags))) for category, tags in categories_and_tags.items()}
    categories_and_tags = dict(sorted(categories_and_tags.items()))
    st.session_state["categories_and_tags"] = categories_and_tags

    # del the tags editing widgets state to prevent overwriting the changes
    for category in categories_and_tags.keys():
        try:
            del st.session_state[f"{category}_tags"]
        except KeyError:  # new category doesn't has a state yet
            pass

    # save the changes to the yaml file
    with open(yaml_path, 'w') as file:
        yaml.dump(categories_and_tags, file)
    st.rerun()


def assure_tags_table(conn: SQLConnection):
    """create the tags table if it doesn't exist"""
    with conn.session as s:
        s.execute(text(f'CREATE TABLE IF NOT EXISTS {tags_table} ({name_col} TEXT PRIMARY KEY, {category_col}'
                       f' TEXT, {tag_col} TEXT, {service_col} TEXT, {account_number_col} TEXT);'))
        s.commit()


def pull_new_cc_names(conn: SQLConnection):
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


def pull_new_bank_names(conn: SQLConnection):
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


def tag_new_cc_data(conn: SQLConnection, categories_and_tags: dict[str: list[str]]):
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


def tag_new_bank_data(conn: SQLConnection, categories_and_tags: dict[str: list[str]]):
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


def edit_auto_tagger_data(conn: SQLConnection, service: Literal['credit card', 'bank'],
                          categories_and_tags: dict[str: list[str]]):
    """edit tagged credit card data within the tags table"""
    match service:
        case 'credit card':
            service = Services.CREDIT_CARD.value
        case 'bank':
            service = Services.BANK.value
        case _:
            raise ValueError(f"Invalid service name: {service}")

    tagged_data = conn.query(
        f"SELECT * FROM {tags_table} "
        f"WHERE {category_col} is not Null "
        f"AND {service_col}=:service;",
        params={'service': service},
        ttl=0)
    if tagged_data.empty:
        st.write("No data to edit")
        return

    # editable table to edit the tagged data
    edited_tagged_data = st.data_editor(tagged_data[[name_col, category_col, tag_col]],
                                        hide_index=True, width=800, key=f'edit_{service}_tagged_data')
    if st.button('Save', key=f'save_edited_{service}_tagged_data'):
        # keep only the modified rows
        edited_tagged_data = edited_tagged_data[(edited_tagged_data[category_col] != tagged_data[category_col]) |
                                                (edited_tagged_data[tag_col] != tagged_data[tag_col])]
        # save the edited data to the database
        with conn.session as s:
            for i, row in edited_tagged_data.iterrows():
                category, tag = format_category_or_tag_strings(row[category_col], row[tag_col])
                verify_category_and_tag(category, tag, categories_and_tags)

                query = text(f'UPDATE {tags_table} SET {category_col}=:category, {tag_col}=:tag'
                             f' WHERE {name_col}=:name AND {service_col}=:service;')
                params = {
                    'category': category if category != '' else None,
                    'tag': tag if category != '' else None,
                    'name': row[name_col],
                    'service': service
                }
                s.execute(query, params)
                s.commit()
        st.rerun()


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
    assert all(isinstance(arg, str) or arg is None or np.isnan(arg) for arg in args), 'all arguments should be strings'
    strings = tuple(arg.title() if isinstance(arg, str) and arg != '' else None for arg in args)
    if len(strings) == 1:
        return strings[0]
    return strings  # type: ignore


def verify_category_and_tag(category: str, tag: str, categories_and_tags: dict[str: list[str]]) -> bool:
    """
    verify that the category and tag are valid

    Parameters
    ----------
    category: str
        the category to verify
    tag: str
        the tag to verify
    categories_and_tags: dict
        a dictionary of categories and their tags

    Returns
    -------
    bool
        True if the category and tag are valid, False otherwise
    """
    if category is None and tag is None:
        return True

    if (category is None and tag is not None) or (category is not None and tag is None):
        st.error('Category and tag should be both None or both not None. please delete both fields or fill them both.')
        return False

    if category not in categories_and_tags.keys():
        st.error(f'Category "{category}" does not exist. Please select a valid category.'
                 f'In case you want to add a new category, please do so in the "Categories & Tags" tab.')
        return False

    if tag is None:
        st.error(f'Tag cannot be empty while setting a category. Please select a valid tag from the following list:\n'
                 f'{categories_and_tags[category]}.')
        return False

    if tag not in categories_and_tags[category]:
        st.error(f'Tag "{tag}" does not exist in the category "{category}". Please select a valid tag from the following'
                 f' list:\n{categories_and_tags[category]}.\n'
                 f'In case you want to add a new tag, please do so in the "Categories & Tags" tab.')
        return False

    return True


def edit_raw_data_tags(conn: SQLConnection, categories_and_tags: dict[str: list[str]]):
    """edit the tags of the raw data in the credit card and bank tables"""
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
            if not edited_data.empty:
                edited_data[[category_col, tag_col]] = edited_data.apply(
                        lambda row: pd.Series(format_category_or_tag_strings(row[category_col], row[tag_col])),
                        axis=1
                    )
                verifications = edited_data.apply(
                    lambda row: verify_category_and_tag(row[category_col], row[tag_col], categories_and_tags),
                    axis=1
                )
                if not verifications.all():
                    st.error('Please fix the errors before saving the data.')

            if st.form_submit_button(label='Save'):
                if not edited_data.empty:
                    if verifications.all():
                        DataUtils.update_db_table(conn, table_type, edited_data)
                    else:
                        st.stop()
                st.rerun()


conn_ = DataUtils.get_db_connection()
categories_and_tags_ = DataUtils.get_categories_and_tags()
assure_tags_table(conn_)
tab_tags, tab_auto_tagger, tab_raw_data = st.tabs(["Categories & Tags", "Automatic Tagger", "Raw Data"])

with tab_tags:
    edit_categories_and_tags(categories_and_tags_, CATEGORIES_PATH, conn_)

with tab_auto_tagger:
    st.caption("<p style='font-size:20px;'>"
               "The automatic tagger will tag new data according to the rules you set here"
               "</p>",
               unsafe_allow_html=True)
    pull_new_cc_names(conn_)
    pull_new_bank_names(conn_)
    cc_tab, bank_tab = st.tabs(["Credit Card", "Bank"])

    with cc_tab:
        tag_new_cc_data(conn_, categories_and_tags_)
        edit_auto_tagger_data(conn_, 'credit card', categories_and_tags_)

    with bank_tab:
        tag_new_bank_data(conn_, categories_and_tags_)
        edit_auto_tagger_data(conn_, 'bank', categories_and_tags_)

with (tab_raw_data):
    edit_raw_data_tags(conn_, categories_and_tags_)
