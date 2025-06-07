import streamlit as st
from typing import List
from fad.app.services.tagging_service import CategoriesTagsService, AutomaticTaggerService
from fad.app.naming_conventions import NonExpensesCategories
from ..utils.data import get_db_connection
import streamlit_antd_components as sac
from typing import Literal
from fad.app.utils.widgets import PandasFilterWidgets
from fad.app.services.transactions_service import TransactionsService
import pandas as pd


def format_category_or_tag_strings(s: str) -> str:
    if not s:
        return s
    if s.isupper():
        return s.upper()
    return s.title()


class CategoriesTagsEditor:
    def __init__(self):
        self.service = CategoriesTagsService()
        self.protected_categories = [e.value for e in NonExpensesCategories]
    #     # Call the static method to inject CSS
    #     self.inject_css_for_pills()

    # @staticmethod
    # def inject_css_for_pills():
    #     # Generate CSS for all pills widgets using their keys
    #     for category in st.session_state['categories_and_tags'].keys():
    #         widget_key = f"{category}_tags"
    #         st.markdown(
    #             f"""
    #             <style>
    #             .st-key-{widget_key} p {{
    #                 color: #007BFF; /* Blue color */
    #                 font-size: 18px; /* Adjust the font size */
    #             }}
    #             /* Exclude label text from color changes */
    #             .st-key-{widget_key} label div {{
    #                 color: inherit; /* Inherit the default color */
    #             }}
    #             </style>
    #             """,
    #             unsafe_allow_html=True
    #         )

    def render(self):
        # Always reload from session state to reflect latest changes
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.markdown(
            'Pay attention to the special Categories: "Ignore", "Salary", "Other Income", and "Investments".<br>'
            'These categories are used for special purposes in the app and you cannot delete them.',
            unsafe_allow_html=True
        )
        add_col, realloc_col, _ = st.columns([0.15, 0.15, 0.7])
        with add_col:
            st.button('New Category', key='add_new_category_button', on_click=self._add_new_category_dialog)
        with realloc_col:
            st.button('Reallocate Tags', key='reallocate_tags_button', on_click=self._reallocate_tags_dialog)
        # Sort categories alphabetically
        for category in sorted(self.service.categories_and_tags.keys()):
            tags = sorted(self.service.categories_and_tags[category])
            self._view_and_edit_tags(category, tags)
            disable = category in self.protected_categories
            st.button(f'Delete {category}', key=f'delete_{category}', disabled=disable,
                      on_click=self._delete_category_dialog, args=(category,))

    @st.fragment
    def _view_and_edit_tags(self, category: str, tags: List[str]):
        # Always reload from session state to reflect latest changes
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.subheader(category, divider="gray")
        # Use segmented control with multi-selection to display and select multiple tags
        selected_tags = st.pills(
            'Tags',
            options=tags,
            selection_mode='multi',
            format_func=lambda tag: f"🔖 {tag.title()}",  # Add an icon and format tags to title case
            key=f'{category}_tags'
        )
        # Align buttons in the same row
        edit_col, realloc_col, add_col, delete_col, _ = st.columns([1, 1.5, 1, 1.5, 9])
        with edit_col:
            if st.button('Edit Tag', key=f'edit_{category}_tag'):
                if selected_tags:
                    self._edit_tag_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for editing.'
        with realloc_col:
            if st.button('Reallocate Tags', key=f'reallocate_{category}_tags'):
                if selected_tags:
                    self._reallocate_tags_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for reallocation.'
        with add_col:
            if st.button('Add Tag', key=f'add_{category}_tag'):
                self._add_tag_dialog(category)
        with delete_col:
            if st.button('Delete Tag', key=f'delete_{category}_tag'):
                if selected_tags:
                    self._delete_tag_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for deletion.'

        # Display warning message in a separate container
        if 'warning_message' in st.session_state:
            st.warning(st.session_state['warning_message'])
            del st.session_state['warning_message']

    @st.dialog('Edit Tag')
    def _edit_tag_dialog(self, category: str, tags: List[str]):
        edited_tags = {}
        for tag in tags:
            new_tag = st.text_input(f'Edit Tag: {tag}', value=tag, key=f'edit_{category}_{tag}_input')
            edited_tags[tag] = new_tag
        if st.button('Save All', key=f'save_all_edit_{category}_tags'):
            success = True
            for old_tag, new_tag in edited_tags.items():
                if old_tag != new_tag:
                    if not (self.service.delete_tag(category, old_tag) and self.service.add_tag(category, new_tag)):
                        success = False
            if success:
                st.success("All tags updated successfully.")
                st.rerun()
            else:
                st.error("Failed to update some tags.")
        if st.button('Cancel', key=f'cancel_edit_{category}_tags'):
            st.rerun()

    @st.dialog('Add Tag')
    def _add_tag_dialog(self, category: str):
        new_tag = st.text_input('New Tag', key=f'new_{category}_tag_input')
        if st.button('Add', key=f'add_new_{category}_tag'):
            if self.service.add_tag(category, new_tag):
                st.success(f"Tag '{new_tag}' added.")
                st.rerun()
            else:
                st.error("Failed to add tag.")
        if st.button('Cancel', key=f'cancel_add_{category}_tag'):
            st.rerun()

    @st.dialog('Add New Category')
    def _add_new_category_dialog(self):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        new_category = st.text_input('New Category Name', key='new_category')
        if st.button('Add', key='add_category_btn'):
            formatted_category = format_category_or_tag_strings(new_category)
            if self.service.add_category(formatted_category):
                st.success(f"Category '{formatted_category}' added successfully.")
                st.rerun()
            else:
                st.error("Invalid category name or category already exists.")
        if st.button('Cancel', key='cancel_add_category_btn'):
            st.rerun()

    @st.dialog('Reallocate Tags')
    def _reallocate_tags_dialog(self, category: str, selected_tags: List[str]):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        all_categories = sorted(self.service.categories_and_tags.keys())
        # Remove the current category from the list of new categories
        new_category_options = [cat for cat in all_categories if cat != category]
        old_category = category
        if old_category:
            tags_to_select = sorted(self.service.categories_and_tags[old_category])
            tags_to_reallocate = selected_tags
            new_category = st.selectbox('Select new category', new_category_options, key='new_category', index=None)
            if old_category and new_category and tags_to_reallocate:
                if st.button('Continue', key='continue_reallocate_tags'):
                    formatted_tags = sorted([format_category_or_tag_strings(tag) for tag in tags_to_reallocate])
                    if self.service.reallocate_tags(old_category, new_category, formatted_tags):
                        st.success("Tags reallocated successfully.")
                        st.rerun()
                    else:
                        st.error("Failed to reallocate tags.")
        if st.button('Cancel', key='cancel_reallocate_tags_btn'):
            st.rerun()

    @st.dialog('Confirm Deletion')
    def _delete_category_dialog(self, category: str):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.write(f'Are you sure you want to delete the "{category}" category?')
        if st.button('Yes', key=f'confirm_delete_{category}'):
            if self.service.delete_category(category, self.protected_categories):
                st.success(f"Category '{category}' deleted successfully.")
                st.rerun()
            else:
                st.error("Cannot delete this category.")
        if st.button('No', key=f'cancel_delete_{category}'):
            st.rerun()

    @st.dialog('Delete Tag')
    def _delete_tag_dialog(self, category: str, tags: List[str]):
        st.write(f'Are you sure you want to delete the selected tags?')
        if st.button('Yes', key=f'confirm_delete_{category}_tags'):
            success = True
            for tag in tags:
                if not self.service.delete_tag(category, tag):
                    success = False
            if success:
                st.success("Tags deleted successfully.")
                st.rerun()
            else:
                st.error("Failed to delete some tags.")
        if st.button('No', key=f'cancel_delete_{category}_tags'):
            st.rerun()


class AutomaticTaggerComponent:
    def __init__(self):
        self.service = AutomaticTaggerService(get_db_connection())
        self.categories_and_tags = st.session_state['categories_and_tags']

    def render(self):
        cc_tab, bank_tab = st.tabs(["Credit Card", "Bank"])
        with cc_tab:
            names = self.service.get_cc_without_rules()
            self.add_rules('credit_card', names)

            st.divider()
            self.edit_rules('credit_card')

        with bank_tab:
            names = self.service.get_bank_without_rules()
            names, account_numbers = zip(*names)
            self.add_rules('bank', names, account_numbers)

            st.divider()
            self.edit_rules('bank')

    def add_rules(self, service: Literal['credit_card', 'bank'], names: List[str], account_numbers: list[str] = None) -> None:
        """
        UI for setting new rules for the auto tagger based on the service and names provided.

        Parameters
        ----------
        service : str
            The service for which to set new rules (e.g., 'credit_card', 'bank').
        names : List[str]
            A list of names for which to set new rules.
        account_numbers : list[str] | None
            A list of account numbers corresponding to the names, required if service is 'bank'. Defaults to None.
        """
        if service == 'credit_card':
            self._add_rules_container(names, service=service)
        elif service == 'bank':
            for account_number in sorted(list(set(account_numbers))):
                account_name, account_provider = self.service.get_bank_account_details(account_number)

                st.subheader(f'Set new rule for {account_name} - {account_provider}: {account_number}')
                curr_names = [name for name, acc_num in zip(names, account_numbers) if acc_num == account_number]
                self._add_rules_container(curr_names, service=service, account_number=account_number)
        else:
            raise ValueError(f"Invalid service name: {service}")

    def _add_rules_container(self, names: list[str], service: Literal['credit_card', 'bank'], account_number: str = None) -> None:
        if not names:
            st.write("No transactions to set new rules to")
            return

        st.subheader(f'Set new rules')

        names = sorted(names)

        # after adding a rule the df is shorter hence a new widget is created, we want to keep the last selected index
        # to provide a better user experience. it also prevents aggregating unused widgets in the session state.
        prev_index = 0
        for key in st.session_state.keys():
            if key.startswith(f'select_transaction_to_set_rule_{service}'):
                if key == f'select_transaction_to_set_rule_{service}_{len(names)}':
                    continue
                prev_index = st.session_state[key]
                if prev_index >= len(names):
                    prev_index = len(names) - 1
                del st.session_state[key]
                break

        widget_key = f'select_transaction_to_set_rule_{service}_{len(names)}'
        if account_number is not None:
            widget_key += f'_{account_number}'

        idx = sac.buttons(
            items=names,
            index=prev_index,
            radius='lg',
            variant='outline',
            label='Select transaction name to set its rule for the auto tagger',
            return_index=True,
            color='red',
            use_container_width=True,
            key=widget_key,
        )

        name = names[idx]
        self._add_rule_window(name, service, account_number=account_number)

    @st.fragment
    def _add_rule_window(
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
        service : str
            the service of the transaction. Should be one of 'credit_card' or 'bank'.
        account_number : str | None
            the account number of the transaction. If None, the transaction is a credit card transaction. If not None,
            the transaction is a bank transaction

        Returns
        -------
        None
        """
        assert service in ['credit_card', 'bank'], \
            f"Service must be one of 'credit_card' or 'bank', got {service}"

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
            try:
                default_tag = tags.index(default_tag)
            except ValueError:
                default_tag = None

            tag = st.selectbox(
                label="Select a Tag",
                label_visibility="hidden",
                options=tags,
                index=default_tag,
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
                self.service.add_rule(description, category, tag, service, method, account_number)
                st.rerun()

    def edit_rules(self, service: Literal['credit_card', 'bank']):
        """edit the auto tagger rules"""
        name_col = self.service.auto_tagger_repo.name_col
        category_col = self.service.auto_tagger_repo.category_col
        tag_col = self.service.auto_tagger_repo.tag_col
        account_number_col = self.service.auto_tagger_repo.account_number_col

        df_tags = self.service.auto_tagger_repo.get_table(service=service)
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

        for idx in changes['selection']['rows']:
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
            try:
                default_tag = tags.index(default_tag)
            except ValueError:
                default_tag = None

            tag = st.selectbox(
                label="Select a Tag",
                label_visibility="hidden",
                options=tags,
                index=default_tag,
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
                self.service.update_rule(description, category, tag, service, method, account_number)
                st.rerun()


class ManuallyTaggingComponent:
    def __init__(self):
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService(get_db_connection())

    def render(self):
        st.subheader("Manually Tagging")
        st.markdown(
            "This feature allows you to manually tag transactions that do not have any tags. "
            "You can select a transaction and assign a category and tag to it."
        )
        self.edit_raw_data_tags()

    def edit_raw_data_tags(self):
        """edit the tags of the raw data in the credit card and bank tables"""
        columns_order = self.transactions_service.get_table_columns_for_display()

        names = self.transactions_service.get_table_names_for_display()
        table_name = st.selectbox(
            'Select data table to edit:',
            names,
            key="tagging_raw_data_table_type"
        )
        table_name = table_name.lower().replace(' ', '_').replace('_transactions', '')  # noqa
        data = self.transactions_service.get_table_data_for_display(table_name)
        widget_col, data_col = st.columns([0.3, 0.7])

        # filter the data according to the user's input
        with widget_col:
            # store the class instance in the session state to preserve its state across reruns
            if st.session_state.get(f"manual_tagging_filter_widgets_{table_name}", None) is None:
                widgets_map = {
                    self.transactions_service.transactions_repository.amount_col: 'number_range',
                    self.transactions_service.transactions_repository.date_col: 'date_range',
                    self.transactions_service.transactions_repository.provider_col: 'multiselect',
                    self.transactions_service.transactions_repository.account_name_col: 'multiselect',
                    self.transactions_service.transactions_repository.account_number_col: 'multiselect',
                    self.transactions_service.transactions_repository.desc_col: 'multiselect',
                    self.transactions_service.transactions_repository.category_col: 'multiselect',
                    self.transactions_service.transactions_repository.tag_col: 'multiselect',
                    self.transactions_service.transactions_repository.status_col: 'multiselect',
                    self.transactions_service.transactions_repository.type_col: 'multiselect',
                }

                df_filter = PandasFilterWidgets(data, widgets_map, keys_prefix=table_name)
                st.session_state[f"manual_tagging_filter_widgets_{table_name}"] = df_filter
            else:
                df_filter = st.session_state[f"manual_tagging_filter_widgets_{table_name}"]
            df_filter.display_widgets()
            df_data = df_filter.filter_df()

        # display the data and bulk edit it
        with data_col:
            selections = st.dataframe(
                df_data,
                key=f'{table_name}_transactions_editor',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
            )

            indices = selections['selection']['rows']
            for idx in indices:
                row = df_data.iloc[idx]
                self._manual_tagger_editing_window(row, service=table_name)

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
        assert service in ['credit_card', 'bank'], f"Service must be one of 'credit_card' or 'bank', got {service}"

        name_col = self.transactions_service.transactions_repository.desc_col
        amount_col = self.transactions_service.transactions_repository.amount_col
        tag_col = self.transactions_service.transactions_repository.tag_col
        category_col = self.transactions_service.transactions_repository.category_col
        id_col = self.transactions_service.transactions_repository.id_col

        if st.button("Split Transaction"):
            st.write("Coming Soon...")
            st.button("Back", key='back_from_split_transaction')
        else:
            # Columns for layout
            col_cat, col_tag, col_save = st.columns([0.4, 0.4, 0.2])

            with col_cat:
                categories = list(self.categories_tags_service.categories_and_tags.keys())
                category = st.selectbox(
                    label="Edit Category",
                    options=categories,
                    index=categories.index(row[category_col]) if row[category_col] in categories else None,
                    placeholder='Category',
                    key=f'manual_tagger_select_category_{row[name_col]}'
                )

            with col_tag:
                tags = self.categories_tags_service.categories_and_tags.get(category, [])
                tag = st.selectbox(
                    label="Edit Tag",
                    options=tags,
                    index=tags.index(row[tag_col]) if row[tag_col] in tags else None,
                    placeholder='Tag',
                    key=f'manual_tagger_select_tag_{row[name_col]}'
                )

            with col_save:
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
                if st.button('Save', key=f'save_{row[name_col]}'):
                    self.transactions_service.update_data_table(service, row[id_col], category, tag)
                    st.rerun()

