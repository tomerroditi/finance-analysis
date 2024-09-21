import streamlit as st
import yaml

import pandas as pd
import streamlit_antd_components as sac
from streamlit_tags import st_tags
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection
from typing import Literal

from fad import CATEGORIES_PATH
from fad.app.utils.widgets import PandasFilterWidgets
from fad.app.utils.data import get_categories_and_tags, format_category_or_tag_strings, assure_tags_table, get_table
from fad.app.naming_conventions import (
    Tables,
    NonExpensesCategories,
    TransactionsTableFields,
    Services,
    TagsTableFields,
    CreditCardTableFields,
    BankTableFields,
)


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


class CategoriesAndTags:
    def __init__(self, conn: SQLConnection):
        """
        Initialize the CategoriesAndTags object

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database
        """
        self.categories_and_tags = get_categories_and_tags()
        self.conn = conn

        assure_tags_table(self.conn)

    ########################################################
    # categories and tags editing functions
    ########################################################
    def edit_categories_and_tags(self) -> None:
        """
        The main function to edit the categories and tags. The function displays the categories and tags in the UI and
        allows the user to edit them. The function also allows the user to add new categories, reallocate tags between
        categories, and delete categories.

        Returns
        -------
        None

        """
        st.markdown(
            'Pay attention to the special Categories: "Ignore", "Salary", "Other Income", and "Investments".<br>'
            'These categories are used for special purposes in the app and you cannot delete them.<br>'
            'Read more on how to use them under each category name below (TBC).',
            unsafe_allow_html=True
        )
        # TODO: add detailed instructions on how to use the special categories

        add_cat_col, reallocate_tags_col, _ = st.columns([0.15, 0.15, 0.7])
        # add new categories
        with add_cat_col:
            st.button(
                'New Category', 'add_new_category_button', on_click=self._add_new_category, use_container_width=True
            )

        # reallocate tags
        with reallocate_tags_col:
            st.button(
                'Reallocate Tags', 'reallocate_tags_button', on_click=self._reallocate_tags, use_container_width=True
            )

        # Iterate over a copy of the dictionary's items and display the categories and tags and allow editing
        for category, tags in list(self.categories_and_tags.items()):
            self._view_and_edit_tags(category)

            # delete category
            disable = True if category in [e.value for e in NonExpensesCategories] else False
            st.button(f'Delete {category}', key=f'my_{category}_delete', disabled=disable,
                      on_click=self._delete_category,
                      args=(self.categories_and_tags, category, self.conn, CATEGORIES_PATH))

    @st.fragment
    def _view_and_edit_tags(self, category: str) -> None:
        """
        Display the tags of the given category and allow the user to edit them

        Parameters
        ----------
        category : str
            The category to display its tags

        Returns
        -------
        None
        """
        # TODO: change st_tags to something else due to internal bug in the package that causes many undesired reruns.
        st.subheader(category, divider="gray")
        if category == "Ignore":
            st.write(
                "Transactions that you don't want to consider in the analysis. For example credit card bills in "
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
        tags = self.categories_and_tags[category]
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            new_tags = [format_category_or_tag_strings(tag) for tag in new_tags]
            self.categories_and_tags[category] = new_tags
            # save changes and rerun to update the UI
            self._update_yaml()
            st.rerun()

    @st.dialog('Add New Category')
    def _add_new_category(self) -> None:
        """
        A dialog to add a new category. The user will be prompted to enter the new category name. If the user confirms
        the addition, the new category will be added to the categories and tags dictionary, the yaml file will be
        updated and the script will rerun. If the user cancels the addition, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Returns
        -------
        None
        """
        existing_categories = [k.lower() for k in self.categories_and_tags.keys()]
        new_category = st.text_input('New Category Name', key='new_category')

        if st.button('Cancel'):
            st.rerun()

        if st.button('Continue') and new_category != '' and new_category is not None:
            if new_category.lower() in existing_categories:
                st.warning(f'The category "{new_category}" already exists. Please choose a different name.')
                st.stop()
            self.categories_and_tags[format_category_or_tag_strings(new_category)] = []
            self._update_yaml()
            st.rerun()

    @st.dialog('Reallocate Tags')
    def _reallocate_tags(self) -> None:
        """
        A dialog to reallocate tags from one category to another. The user will be prompted to select the current
        category and the tags to reallocate, then select the new category to reallocate the tags to. If the user
        confirms the reallocation, the tags will be updated in the database and the yaml file and the script will rerun.
        If the user cancels the reallocation, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Returns
        -------
        None
        """
        all_categories = list(self.categories_and_tags.keys())
        old_category = st.selectbox('Select current category', all_categories, index=None,
                                    key='old_category')
        tags_to_select = self.categories_and_tags[old_category] if old_category is not None else []
        tags_to_reallocate = st.multiselect('Select tags to reallocate', tags_to_select, key='reallocate_tags')
        if old_category is not None:
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
                        with (self.conn.session as s):
                            for tag in tags_to_reallocate:
                                query = text(
                                    f'UPDATE {table} SET {curr_category_col}=:new_category WHERE {curr_tag_col}=:tag AND '
                                    f'{curr_category_col}=:old_category;')
                                s.execute(query, {'new_category': new_category, 'tag': tag,
                                                  'old_category': old_category})
                                s.commit()

                    self.categories_and_tags[new_category].extend(tags_to_reallocate)
                    _ = [self.categories_and_tags[old_category].remove(tag) for tag in tags_to_reallocate]
                    self._update_yaml()
                    st.rerun()

    @st.dialog('Confirm Deletion')
    def _delete_category(self, category: str) -> None:
        """
        A dialog to confirm the deletion of the given category. If the user confirms the deletion, the category will be
        deleted from the categories and tags dictionary, the yaml file and raw data tables are updated accordingly and
        the script will rerun. If the user cancels the deletion, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Parameters
        ----------
        category : str
            The category to delete

        Returns
        -------
        None
        """
        st.write(f'Are you sure you want to delete the "{category}" category?')
        st.write('Deleting a category deletes it from the auto tagger rules as well.')
        delete_tags_of_logged_data = st.checkbox('Delete tags of logged data', key=f'delete_tags_of_logged_data')
        confirm_button = st.button('Continue', key=f'continue_delete_category')
        cancel_button = st.button('Cancel', key=f'cancel_delete_category')

        if confirm_button:
            data_to_delete = self.conn.query(f'SELECT {name_col} FROM {tags_table} WHERE {category_col}=:category',
                                             params={'category': category}, ttl=0)

            with self.conn.session as s:
                for i, row in data_to_delete.iterrows():
                    query = text(f"UPDATE {tags_table} SET {category_col}=Null, {tag_col}=Null WHERE {name_col}=:name")
                    s.execute(query, {'name': row[name_col]})
                    s.commit()

            if delete_tags_of_logged_data:
                self._update_raw_data_deleted_category(category)

            del self.categories_and_tags[category]
            self._update_yaml()
            st.rerun()

        if cancel_button:
            st.rerun()

    def _update_raw_data_deleted_category(self, category: str) -> None:
        """
        Updates tags and category of deleted category in the raw data tables to Null

        Parameters
        ----------
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
            with self.conn.session as s:
                query = text(f"UPDATE {table} SET {curr_category_col}=Null, {curr_tag_col}=Null "
                             f"WHERE {curr_category_col}=:category")
                s.execute(query, {'category': category})
                s.commit()

    def _update_yaml(self) -> None:
        """
        update the yaml file with the current state of the categories and tags and rerun the app.

        Returns
        -------
        None
        """
        # sort the categories and tags by alphabetical order
        categories_and_tags = {category: sorted(list(set(tags))) for category, tags in self.categories_and_tags.items()}
        categories_and_tags = dict(sorted(categories_and_tags.items()))
        st.session_state["categories_and_tags"] = categories_and_tags

        # del the tags editing widgets state to prevent overwriting the changes
        for category in categories_and_tags.keys():
            try:
                del st.session_state[f"{category}_tags"]
            except KeyError:  # new category doesn't have a state yet
                pass

        # save the changes to the yaml file
        with open(CATEGORIES_PATH, 'w') as file:
            yaml.dump(categories_and_tags, file)

    ########################################################
    # auto tagger functions
    ########################################################
    def pull_new_transactions_names(self) -> None:
        """
        pull new transactions names from the credit card and bank tables and insert them into the tags table

        Returns
        -------
        None
        """
        self._pull_new_cc_names()
        self._pull_new_bank_names()

    def _pull_new_cc_names(self):
        """pull new credit card transactions names from the credit card table and insert them into the tags table"""
        current_cc_names = self.conn.query(
            f"SELECT {name_col} FROM {tags_table} WHERE {service_col}='credit_card';", ttl=0
        )
        cc_names = self.conn.query(f"SELECT {cc_desc_col} FROM {credit_card_table};", ttl=0)
        new_cc_names = cc_names.loc[~cc_names[cc_desc_col].isin(current_cc_names[name_col]), cc_desc_col].unique()
        with self.conn.session as s:
            for name in new_cc_names:
                s.execute(
                    text(f'INSERT INTO {tags_table} ({name_col}, {service_col}) VALUES (:curr_name, "credit_card");'),
                    {'curr_name': name})
            s.commit()

    def _pull_new_bank_names(self):
        """pull new bank transactions names from the bank table and insert them into the tags table"""
        current_banks_names = self.conn.query(
            f"SELECT {name_col}, {account_number_col} FROM {tags_table} WHERE {service_col} = 'bank';", ttl=0
        )
        bank_names = self.conn.query(f"SELECT {bank_desc_col}, {bank_account_number_col} FROM {bank_table};", ttl=0)
        bank_names = bank_names.rename(columns={bank_desc_col: name_col, bank_account_number_col: account_number_col})

        new_bank_names = current_banks_names.merge(bank_names, on=[name_col, account_number_col], how='outer', indicator=True)
        new_bank_names = new_bank_names[new_bank_names['_merge'] == 'right_only'].drop('_merge', axis=1)
        new_bank_names = new_bank_names.drop_duplicates(subset=[name_col, account_number_col])
        with self.conn.session as s:
            for i, row in new_bank_names.iterrows():
                s.execute(text(f'INSERT INTO {tags_table} ({name_col}, {account_number_col}, {service_col})'
                               f' VALUES (:curr_name, :curr_account_number, "bank");'),
                          {'curr_name': row[name_col], 'curr_account_number': row[account_number_col]})
            s.commit()

    def edit_auto_tagger_data(self, service: Literal['credit card', 'bank']):
        """edit tagged credit card data within the tags table"""
        match service:
            case 'credit card':
                service = Services.CREDIT_CARD.value
            case 'bank':
                service = Services.BANK.value
            case _:
                raise ValueError(f"Invalid service name: {service}")

        tagged_data = self.conn.query(
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
            with self.conn.session as s:
                for i, row in edited_tagged_data.iterrows():
                    category, tag = format_category_or_tag_strings(row[category_col], row[tag_col])
                    self._verify_category_and_tag(category, tag)

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

    def tag_new_cc_data(self):
        """tag new credit card data"""

        df_tags = self.conn.query(f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL) AND {service_col} = 'credit_card';
            """,
                                  ttl=0
                                  )
        if df_tags.empty:
            st.write("No data to tag")
            return

        # editable table to tag the data
        categories = list(self.categories_and_tags.keys())
        tags = [f'{category}: {tag}' for category in categories for tag in self.categories_and_tags[category]]
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
                with self.conn.session as s:
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

    def tag_new_bank_data(self):
        """tag new bank data"""
        df_tags = self.conn.query(f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL)
            AND {service_col} = 'bank';
            """,
                                  ttl=0)
        if df_tags.empty:
            st.write("No data to tag")
            return

        # editable table to tag the data
        categories = list(self.categories_and_tags.keys())
        tags = [f'{category}: {tag}' for category in categories for tag in self.categories_and_tags[category]]
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
                with self.conn.session as s:
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

    def set_auto_tagger_rules(self, service: Literal['credit_card', 'bank']):
        """tag new credit card data"""
        df_tags = self.conn.query(
            f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL) AND {service_col} = :service;
            """,
            params={'service': service},
            ttl=0
        )

        if df_tags.empty:
            st.write("No transactions to set new rules to")
            return

        if service == 'credit_card':
            st.subheader(f'Set new rules')
            self._set_auto_tagger_rules_container(df_tags)
        elif service == 'bank':
            for account_number in df_tags[account_number_col].unique():
                account_name_and_provider = self.conn.query(
                    f"""
                    SELECT {bank_account_name_col}, {bank_provider_col} 
                    FROM {bank_table} 
                    WHERE {account_number_col}=:account_number 
                    LIMIT 1;
                    """,
                    params={'account_number': account_number},
                    ttl=0
                )
                account_name = account_name_and_provider[bank_account_name_col].iloc[0]
                account_provider = account_name_and_provider[bank_provider_col].iloc[0]
                st.subheader(f'Set new rule for {account_name} - {account_provider}: {account_number}')
                df = df_tags[df_tags[account_number_col] == account_number]
                self._set_auto_tagger_rules_container(df)
        else:
            raise ValueError(f"Invalid service name: {service}")

    def _set_auto_tagger_rules_container(self, df: pd.DataFrame):
        df = df.copy()
        df = df.sort_values(by=name_col)
        idx = sac.buttons(
            items=df[name_col].tolist(),
            index=0,
            radius='lg',
            variant='outline',
            label='Select transaction to set its rule for the auto tagger',
            return_index=True,
            color='red',
            use_container_width=True,
        )

        if idx is not None:
            row = df.iloc[idx]
            self._auto_tagger_editing_window(row[name_col], row[service_col], account_number=row[account_number_col])

    def edit_auto_tagger_rules(self, service: Literal['credit_card', 'bank']):
        """edit the auto tagger rules"""
        df_tags = self.conn.query(
            f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NOT NULL OR {tag_col} IS NOT NULL) AND {service_col} = :service;
            """,
            params={'service': service},
            ttl=0
        )

        st.subheader(f'Edit auto tagger rules')

        if df_tags.empty:
            st.write("No rules to edit")
            return

        df_tags = df_tags.sort_values(by=name_col)
        if service == 'credit_card':
            cols = [name_col, category_col, tag_col]
        elif service == 'bank':
            cols = [name_col, account_number_col, category_col, tag_col]
        else:
            raise ValueError(f"Invalid service name: {service}")

        changes = st.dataframe(
            df_tags,
            on_select='rerun',
            selection_mode='single-row',
            column_order=cols,
            hide_index=True,
            use_container_width=True
        )

        indices = changes['selection']['rows']
        for idx in indices:
            row = df_tags.iloc[idx]
            self._auto_tagger_editing_window(row[name_col], service, row[account_number_col], row[category_col],
                                             row[tag_col])

    @st.fragment
    def _auto_tagger_editing_window(
            self,
            description: str,
            service: Literal['credit_card', 'bank'],
            account_number: str,
            default_category: str | None = None,
            default_tag: str | None = None,
    ):
        """
        a fragment to tag new data for the auto tagger. The fragment displays the description of the transaction and
        allow the user to select the category and tag for the transaction. it contains a save button to save the
        selection.

        Parameters
        ----------
        description : str
            the description of the transaction
        service : Literal['credit_card', 'bank']
            the service of the transaction. Should be one of 'credit_card' or 'bank'.
        account_number : str | None
            the account number of the transaction. If None, the transaction is a credit card transaction. If not None,
            the transaction is a bank transaction

        Returns
        -------
        None
        """
        # Columns for layout
        catg_col_, tag_col_, update_method_col_, save_col_ = st.columns([0.2, 0.2, 0.2, 0.2])

        with catg_col_:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                label="Select a Category",
                label_visibility="hidden",
                options=categories,
                index=None if default_category is None else categories.index(default_category),
                placeholder='Category',
                key=f'select_category_{description}_{service}_{account_number}_auto_tagger'
            )

        with tag_col_:
            tags = self.categories_and_tags.get(category, [])
            tag = st.selectbox(
                label="Select a Tag",
                label_visibility="hidden",
                options=tags,
                index=None if default_tag is None else tags.index(default_tag),
                placeholder='Tag',
                key=f'select_tag_{description}_{service}_{account_number}_auto_tagger'
            )

        with update_method_col_:
            method = st.selectbox(
                label='method',
                label_visibility="hidden",
                options=["All", "From now on"],
                index=0,
                placeholder="How to update",
                key=f'select_method_{description}_{service}_{account_number}_auto_tagger',
                help="Select 'All' to tag all of this transaction's occurrences. Select 'From now on'"
                     " to keep old tags and tag only future occurrences.")

        with save_col_:
            st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
            if st.button('Save', key=f'save_{description}_{service}_{account_number}_auto_tagger'):
                if category is None or tag is None:
                    st.error('Please select both a category and a tag before saving.')
                self._update_auto_tagger_table(description, category, tag, service, method, account_number)
                st.rerun()

    def _update_auto_tagger_table(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                                  method: Literal['All', 'From now on'], account_number: str | None = None) -> None:
        """update the auto tagger rules in the database"""
        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name,
                'service_val': service
            }

            if service == 'credit_card':
                my_query = f"""
                    UPDATE {tags_table}
                    SET {category_col} = :category_val, {tag_col} = :tag_val
                    WHERE {name_col} = :name_val AND {service_col} = :service_val
                """
            elif service == 'bank':
                if account_number is None:
                    raise ValueError("account_number should be provided for bank transactions tagging")
                my_query = f"""
                    UPDATE {tags_table}
                    SET {category_col} = :category_val, {tag_col} = :tag_val
                    WHERE {name_col} = :name_val AND {service_col} = :service_val AND {account_number_col} = :account_number_val
                """
                params['account_number_val'] = account_number

            s.execute(text(my_query), params)
            s.commit()

        if method == 'All':
            self._update_raw_data_tags(name, category, tag, service, account_number)
        elif method == 'From now on':
            pass  # do nothing
        else:
            raise ValueError(f"Invalid auto tagger update method: {method}")

    def _update_raw_data_tags(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                              account_number: str | None = None) -> None:
        """
        update the tags of the raw data in the credit card and bank tables. If overwrite is True, all occurrences of the
        transaction with the name supplied will be updated. If overwrite is False, only transactions without a tag will
        be updated.

        Parameters
        ----------
        name : str
            the name of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with
        service : str
            the service of the transaction, should be one of 'credit_card' or 'bank'
        account_number : str | None
            the account number of the transaction, only used for bank transactions. If None, all transactions with the
            name supplied will be updated

        Returns
        -------
        None
        """
        if service == 'credit_card':
            table = credit_card_table
            name_col_ = cc_desc_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
        elif service == 'bank':
            table = bank_table
            name_col_ = bank_desc_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name
            }

            if service == 'credit_card':
                my_query = f"""
                    UPDATE {table}
                    SET {category_col_} = :category_val, {tag_col_} = :tag_val
                    WHERE {name_col_} = :name_val
                """
            elif service == 'bank':
                if account_number is None:
                    raise ValueError("account_number should be provided for bank transactions tagging")
                my_query = f"""
                    UPDATE {table}
                    SET {category_col_} = :category_val, {tag_col_} = :tag_val
                    WHERE {name_col_} = :name_val AND {bank_account_number_col} = :account_number_val
                """
                params['account_number_val'] = account_number

            s.execute(text(my_query), params)
            s.commit()

    ########################################################
    # manual tagging functions
    ########################################################
    def edit_raw_data_tags(self):
        """edit the tags of the raw data in the credit card and bank tables"""
        credit_card_data = get_table(self.conn, credit_card_table)
        bank_data = get_table(self.conn, bank_table)

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

        widget_col, data_col = st.columns([0.3, 0.7])

        # filter the data according to the user's input
        with widget_col:
            if st.session_state.get(f"manual_tagging_filter_widgets_{table_type}", None) is None:
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
                df_filter = PandasFilterWidgets(df_data, widgets_map, keys_prefix=prefix)
                st.session_state[f"manual_tagging_filter_widgets_{table_type}"] = df_filter
            else:
                df_filter = st.session_state[f"manual_tagging_filter_widgets_{table_type}"]
            df_filter.display_widgets()
            df_data = df_filter.filter_df()

        # display the data and bulk edit it
        with data_col:
            selections = st.dataframe(
                df_data,
                key=f'{prefix}transactions_editor',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
            )

            indices = selections['selection']['rows']
            service = table_type.replace('_transactions', '')
            for idx in indices:
                row = df_data.iloc[idx]
                self._manual_tagger_editing_window(row, service)

    @st.fragment
    def _manual_tagger_editing_window(self, row: pd.Series, service: Literal['credit_card', 'bank']):
        """
        a fragment to tag new data for the manual tagger. The fragment displays the description of the transaction and
        allow the user to select the category and tag for the transaction. it contains a save button to save the
        selection.

        Parameters
        ----------
        row : pd.Series
            the row of the transaction
        service : Literal['credit_card', 'bank']
            the service of the transaction. Should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        if service == 'bank':
            name_col_ = bank_desc_col
            amount_col_ = bank_amount_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
            id_col_ = bank_id_col
        elif service == 'credit_card':
            name_col_ = cc_desc_col
            amount_col_ = cc_amount_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
            id_col_ = cc_id_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        if st.button("Split Transaction"):
            st.write("Coming Soon...")
            st.button("Back", key='back_from_split_transaction')
        else:
            # Columns for layout
            col_cat, col_tag, col_save = st.columns([0.4, 0.4, 0.2])

            with col_cat:
                categories = list(self.categories_and_tags.keys())
                category = st.selectbox(
                    label="Edit Category",
                    options=categories,
                    index=categories.index(row[category_col_]) if row[category_col_] in categories else None,
                    placeholder='Category',
                    key=f'manual_tagger_select_category_{row[name_col_]}'
                )

            with col_tag:
                tags = self.categories_and_tags.get(category, [])
                tag = st.selectbox(
                    label="Edit Tag",
                    options=tags,
                    index=tags.index(row[tag_col_]) if row[tag_col_] in tags else None,
                    placeholder='Tag',
                    key=f'manual_tagger_select_tag_{row[name_col_]}'
                )

            with col_save:
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
                if st.button('Save', key=f'save_{row[name_col_]}'):
                    self._update_data_table(service, row[id_col_], category, tag)
                    st.rerun()

    def _update_data_table(self, service: Literal['credit_card', 'bank'], id_: int, category: str, tag: str) -> None:
        """
        update the tags of the raw data in the credit card and bank tables.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            the service of the transaction, should be one of 'credit_card' or 'bank'
        id_ : int
            the id of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with

        Returns
        -------
        None
        """
        if service == 'credit_card':
            table = credit_card_table
            id_col_ = cc_id_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
        elif service == 'bank':
            table = bank_table
            id_col_ = bank_id_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'id_val': id_
            }

            my_query = f"""
                UPDATE {table}
                SET {category_col_} = :category_val, {tag_col_} = :tag_val
                WHERE {id_col_} = :id_val
            """

            s.execute(text(my_query), params)
            s.commit()

    ########################################################
    # helper functions
    ########################################################
    def _verify_category_and_tag(self, category: str, tag: str) -> bool:
        """
        verify that the category and tag are valid

        Parameters
        ----------
        category: str
            the category to verify
        tag: str
            the tag to verify

        Returns
        -------
        bool
            True if the category and tag are valid, False otherwise
        """
        if category is None and tag is None:
            return True

        if (category is None and tag is not None) or (category is not None and tag is None):
            st.error(
                'Category and tag should be both None or both not None. please delete both fields or fill them both.')
            return False

        if category not in self.categories_and_tags.keys():
            st.error(f'Category "{category}" does not exist. Please select a valid category.'
                     f'In case you want to add a new category, please do so in the "Categories & Tags" tab.')
            return False

        if tag is None:
            st.error(
                f'Tag cannot be empty while setting a category. Please select a valid tag from the following list:\n'
                f'{self.categories_and_tags[category]}.')
            return False

        if tag not in self.categories_and_tags[category]:
            st.error(
                f'Tag "{tag}" does not exist in the category "{category}". Please select a valid tag from the following'
                f' list:\n{self.categories_and_tags[category]}.\n'
                f'In case you want to add a new tag, please do so in the "Categories & Tags" tab.')
            return False

        return True

    def update_raw_data_by_rules(self):
        """
        Update the raw data by the auto tagger rules
        """
        self._update_raw_data_by_rules_credit_card()
        self._update_raw_data_by_rules_bank()

    def _update_raw_data_by_rules_credit_card(self):
        """
        Update the credit card raw data by the auto tagger rules
        """
        with self.conn.session as s:
            query = text(f"""
                UPDATE {credit_card_table}
                SET {cc_category_col} = {tags_table}.{category_col}, {cc_tag_col} = {tags_table}.{tag_col}
                FROM {tags_table}
                WHERE {credit_card_table}.{cc_desc_col} = {tags_table}.{name_col}
                AND {tags_table}.{service_col} = 'credit_card'
                AND {credit_card_table}.{cc_category_col} IS NULL
            """)
            s.execute(query)
            s.commit()

    def _update_raw_data_by_rules_bank(self):
        """
        Update the bank raw data by the auto tagger rules
        """
        with self.conn.session as s:
            query = text(f"""
                UPDATE {bank_table}
                SET {bank_category_col} = {tags_table}.{category_col}, {bank_tag_col} = {tags_table}.{tag_col}
                FROM {tags_table}
                WHERE {bank_table}.{bank_desc_col} = {tags_table}.{name_col}
                AND {bank_table}.{bank_account_number_col} = {tags_table}.{account_number_col}
                AND {tags_table}.{service_col} = 'bank'
                AND {bank_table}.{bank_category_col} IS NULL
            """)
            s.execute(query)
            s.commit()
