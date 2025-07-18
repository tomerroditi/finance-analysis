from typing import List
from typing import Literal

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from fad.app.naming_conventions import NonExpensesCategories
from fad.app.services.split_transactions_service import SplitTransactionsService
from fad.app.services.tagging_service import CategoriesTagsService, AutomaticTaggerService
from fad.app.services.transactions_service import TransactionsService
from fad.app.utils.widgets import PandasFilterWidgets


def format_category_or_tag_strings(s: str) -> str:
    """
    Format category or tag strings for consistent display.

    Parameters
    ----------
    s : str
        The string to format.

    Returns
    -------
    str
        The formatted string. If the string is all uppercase, it remains uppercase.
        Otherwise, it is converted to title case.
    """
    if not s:
        return s
    if s.isupper():
        return s.upper()
    return s.title()


class CategoriesTagsEditor:
    """
    Component for managing categories and tags in the application.

    This class provides UI components and functionality for viewing, adding, editing,
    and deleting categories and tags. It also handles the reallocation of tags between
    categories. Some categories are protected and cannot be deleted.

    Attributes
    ----------
    service : CategoriesTagsService
        Service for managing categories and tags data.
    protected_categories : list[str]
        List of category names that cannot be deleted.
    """
    # List of (category, tag) pairs that cannot be deleted
    PROTECTED_CATEGORY_TAGS = [
        ("Other", "No tag"),
        # Add more (category, tag) pairs here as needed
    ]
    def __init__(self):
        """
        Initialize the CategoriesTagsEditor.

        Creates an instance of CategoriesTagsService and sets up the list of
        protected categories that cannot be deleted.
        """
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

    def render(self) -> None:
        """
        Render the categories and tags editor UI.

        Displays all categories and their associated tags, along with buttons for
        adding, editing, and deleting categories and tags. Protected categories
        cannot be deleted. Categories and tags are displayed in alphabetical order.

        Returns
        -------
        None
            Renders UI components in the Streamlit app.
        """
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
    def _view_and_edit_tags(self, category: str, tags: List[str]) -> None:
        """
        Display and provide editing capabilities for tags within a category.

        Creates a UI section for a specific category, displaying all its tags as
        selectable pills. Provides buttons for editing, reallocating, adding, and
        deleting tags. Shows warning messages when actions cannot be performed.

        Parameters
        ----------
        category : str
            The name of the category whose tags are being displayed.
        tags : List[str]
            List of tag names associated with the category.

        Returns
        -------
        None
            Renders UI components for viewing and editing tags.
        """
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
        # Determine which tags are protected for this category
        protected_tags = [tag for (cat, tag) in self.PROTECTED_CATEGORY_TAGS if cat == category]
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
            # Disable delete if any selected tag is protected
            protected_selected_tags = [tag for tag in selected_tags if (category, tag) in self.PROTECTED_CATEGORY_TAGS]
            disable_delete = bool(protected_selected_tags)
            if st.button('Delete Tag', key=f'delete_{category}_tag', disabled=disable_delete):
                if selected_tags:
                    self._delete_tag_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for deletion.'
            if disable_delete and selected_tags:
                st.info(f"The following selected tags are protected and cannot be deleted: {', '.join(protected_selected_tags)}")

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
    """
    Component for managing automatic tagging rules for financial transactions.

    This class provides UI components and functionality for creating, editing, and
    managing rules that automatically assign categories and tags to transactions
    based on their descriptions. It handles both credit card and bank transactions.

    Attributes
    ----------
    service : AutomaticTaggerService
        Service for managing automatic tagging rules.
    categories_and_tags : dict
        Dictionary mapping categories to their associated tags.
    """
    def __init__(self):
        """
        Initialize the AutomaticTaggerComponent.

        Creates an instance of AutomaticTaggerService and retrieves the categories
        and tags from the session state.
        """
        self.service = AutomaticTaggerService()
        self.transactions_service = TransactionsService()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def render(self) -> None:
        """
        Render the automatic tagger component UI.

        Creates tabs for credit card and bank transactions, each containing sections
        for adding new rules and editing existing rules. For transactions without
        existing rules, provides interfaces to create new tagging rules.

        Returns
        -------
        None
            Renders UI components in the Streamlit app.
        """
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
            if key.startswith(f'select_transaction_to_set_rule_{service}_{account_number}'):
                if key == f'select_transaction_to_set_rule_{service}_{account_number}_{len(names)}':
                    continue
                prev_index = st.session_state[key]
                if prev_index >= len(names):
                    prev_index = len(names) - 1
                del st.session_state[key]
                break

        widget_key = f'select_transaction_to_set_rule_{service}_{account_number}_{len(names)}'

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

        # display the transactions of that description
        data = self.transactions_service.get_data_by_description(description, service)
        st.dataframe(data)

    def edit_rules(self, service: Literal['credit_card', 'bank']):
        """edit the auto tagger rules"""
        name_col = self.service.auto_tagger_repo.name_col
        category_col = self.service.auto_tagger_repo.category_col
        tag_col = self.service.auto_tagger_repo.tag_col
        account_number_col = self.service.auto_tagger_repo.account_number_col
        id_col = self.service.auto_tagger_repo.id_col

        df_tags = self.service.auto_tagger_repo.get_table(service=service)
        st.subheader(f'Edit auto tagger rules')

        if df_tags.empty:
            st.write("No rules to edit")
            return

        df_tags = df_tags.sort_values(by=name_col)
        if service == 'credit_card':
            cols = [id_col, name_col, category_col, tag_col]
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
                self._auto_tagger_editing_window(row[id_col], row[name_col], service, row[account_number_col], row[category_col], row[tag_col])
        elif service == 'bank':
            cols = [id_col, name_col, account_number_col, category_col, tag_col]
            for account_number in sorted(df_tags[account_number_col].unique()):
                account_rules = df_tags[df_tags[account_number_col] == account_number]
                # Get account name and provider for the title
                account_name, provider = self.service.get_bank_account_details(account_number)
                st.markdown(f"### {account_name} - {provider}: {account_number}")
                changes = st.dataframe(
                    account_rules,
                    on_select='rerun',
                    selection_mode='single-row',
                    column_order=cols,
                    hide_index=True,
                    use_container_width=True,
                    key=f'edit_rules_table_{account_number}'
                )
                for idx in changes['selection']['rows']:
                    row = account_rules.iloc[idx]
                    self._auto_tagger_editing_window(row[id_col], row[name_col], service, row[account_number_col], row[category_col], row[tag_col])
        else:
            raise ValueError(f"Invalid service name: {service}")

    @st.fragment
    def _auto_tagger_editing_window(
            self,
            id_: int,
            description: str,
            service: Literal['credit_card', 'bank'],
            account_number: str,
            default_category: str | None = None,
            default_tag: str | None = None,
    ):
        """
        Edit a rule for the auto tagger by id. Allows updating or deleting the rule.
        """
        # Columns for layout
        catg_col_, tag_col_, update_method_col_, save_col_, delete_col_ = st.columns([0.18, 0.18, 0.18, 0.18, 0.18])

        with catg_col_:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                label="Select a Category",
                label_visibility="hidden",
                options=categories,
                index=None if default_category is None else categories.index(default_category),
                placeholder='Category',
                key=f'select_category_{id_}_auto_tagger'
            )

        with tag_col_:
            tags = self.categories_and_tags.get(category, [])
            try:
                default_tag_idx = tags.index(default_tag)
            except ValueError:
                default_tag_idx = None

            tag = st.selectbox(
                label="Select a Tag",
                label_visibility="hidden",
                options=tags,
                index=default_tag_idx,
                placeholder='Tag',
                key=f'select_tag_{id_}_auto_tagger'
            )

        with update_method_col_:
            method = st.selectbox(
                label='method',
                label_visibility="hidden",
                options=["All", "From now on"],
                index=0,
                placeholder="How to update",
                key=f'select_method_{id_}_auto_tagger',
                help="Select 'All' to tag all of this transaction's occurrences. Select 'From now on'"
                     " to keep old tags and tag only future occurrences.")

        with save_col_:
            st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
            if st.button('Save', key=f'save_{id_}_auto_tagger'):
                if category is None or tag is None:
                    st.error('Please select both a category and a tag before saving.')
                self.service.update_rule_by_id(id_, category, tag)
                if method == 'All':
                    # Optionally update all matching transactions
                    pass  # Add logic if needed
                st.rerun()

        with delete_col_:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Delete', key=f'delete_{id_}_auto_tagger'):
                self.service.delete_rule_by_id(int(id_))
                st.success("Rule deleted successfully.")
                st.rerun()


class ManuallyTaggingComponent:
    """
    Component for manually tagging financial transactions.

    This class provides UI components and functionality for manually assigning
    categories and tags to transactions that don't have them. It allows users
    to filter and select transactions, then assign appropriate categories and tags.

    Attributes
    ----------
    categories_tags_service : CategoriesTagsService
        Service for managing categories and tags data.
    transactions_service : TransactionsService
        Service for managing transaction data.
    """
    def __init__(self):
        """
        Initialize the ManuallyTaggingComponent.

        Creates instances of CategoriesTagsService, TransactionsService, and
        SplitTransactionsService for managing categories, tags, transaction data,
        and split transactions.
        """
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService()
        self.split_transactions_service = SplitTransactionsService()

    def render(self) -> None:
        """
        Render the manually tagging component UI.

        Displays a header and description of the manual tagging feature,
        then renders the interface for editing tags on raw transaction data.

        Returns
        -------
        None
            Renders UI components in the Streamlit app.
        """
        st.subheader("Manually Tagging")
        st.markdown(
            "This feature allows you to manually tag transactions that do not have any tags. "
            "You can select a transaction and assign a category and tag to it."
        )
        self.edit_raw_data_tags()

    def edit_raw_data_tags(self) -> None:
        """
        Provide interface for editing tags of raw transaction data.

        Creates a UI for selecting a data table (credit card or bank), filtering
        the data, and selecting individual transactions to edit their categories
        and tags. Uses PandasFilterWidgets to provide filtering capabilities.

        Returns
        -------
        None
            Renders UI components for editing transaction tags.
        """
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
        A fragment to tag new data for the manual tagger. The fragment displays the description of the transaction and
        allows the user to select the category and tag for the transaction. It contains a save button to save the
        selection, and a split transaction button to split the transaction into multiple parts.

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
        tag_col = self.transactions_service.transactions_repository.tag_col
        category_col = self.transactions_service.transactions_repository.category_col
        id_col = self.transactions_service.transactions_repository.id_col

        # Check if transaction already has splits
        has_splits = self.split_transactions_service.has_splits(row[id_col], service)

        if has_splits:
            split_button_text = "Edit Split Transaction"
        else:
            split_button_text = "Split Transaction"

        if st.button(split_button_text) or st.session_state.get(f"splits_{service}", [{}])[0].get('id') == row[id_col]:
            self._split_transaction_ui(row, service)
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
                    self.transactions_service.update_tagging_by_id(row[id_col], category, tag, service)
                    # Clear the filter widget cache to force data refresh
                    filter_key = f"manual_tagging_filter_widgets_{service}"
                    if filter_key in st.session_state:
                        del st.session_state[filter_key]
                    st.rerun()

    @st.fragment
    def _split_transaction_ui(self, row: pd.Series, service: Literal['credit_card', 'bank']):
        """
        A fragment to split a transaction into multiple parts. The fragment displays a form for adding
        multiple splits with amount, category, and tag, and validates that the total amount matches
        the original transaction amount.

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
        name_col = self.transactions_service.transactions_repository.desc_col
        amount_col = self.transactions_service.transactions_repository.amount_col
        id_col = self.transactions_service.transactions_repository.id_col
        category_col = self.transactions_service.transactions_repository.category_col
        tag_col = self.transactions_service.transactions_repository.tag_col

        # Get existing splits if any
        existing_splits = self.split_transactions_service.get_splits_for_transaction(row[id_col], service)

        # Initialize session state for splits if not already initialized
        if f"splits_{service}" in st.session_state:
            # Ensure the session state split is of the same data row - update it if not
            if row[id_col] != st.session_state[f"splits_{service}"][0].get('id'):
                st.session_state[f"splits_{service}"] = [
                    {
                        'id': row[id_col],
                        'amount': row[amount_col],
                        'category': '',
                        'tag': ''
                    }
                ]
        else:
            if not existing_splits.empty:
                # Convert existing splits to list of dictionaries
                st.session_state[f"splits_{service}"] = existing_splits.to_dict('records')
            else:
                # Start with one empty split with the full amount
                st.session_state[f"splits_{service}"] = [
                    {
                        'id': row[id_col],
                        'amount': row[amount_col],
                        'category': '',
                        'tag': ''
                    }
                ]

        # Display transaction details
        st.subheader(f"Split Transaction: {row[name_col]}")
        st.write(f"Total Amount: {row[amount_col]}")

        # Display current splits
        st.write("Splits:")

        # Display each split
        for i, split in enumerate(st.session_state[f"splits_{service}"]):
            col1, col2, col3, col4 = st.columns([0.2, 0.3, 0.3, 0.2])

            with col1:
                split['amount'] = st.number_input(
                    "Amount",
                    value=float(split.get('amount', 0)),
                    key=f"split_amount_{i}_{service}",
                )

            with col2:
                categories = list(self.categories_tags_service.categories_and_tags.keys())
                split['category'] = st.selectbox(
                    "Category",
                    options=categories,
                    index=categories.index(split.get('category')) if split.get('category') in categories else None,
                    key=f"split_category_{i}_{service}"
                )

            with col3:
                tags = self.categories_tags_service.categories_and_tags.get(split.get('category', ''), [])
                split['tag'] = st.selectbox(
                    "Tag",
                    options=tags,
                    index=tags.index(split.get('tag')) if split.get('tag') in tags and split.get('tag') else None,
                    key=f"split_tag_{i}_{service}"
                )

            with col4:
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
                disable = len(st.session_state[f"splits_{service}"]) == 1
                if st.button("Remove", key=f"remove_split_{i}_{service}", disabled=disable):
                    st.session_state[f"splits_{service}"].pop(i)
                    st.rerun()

        # Add button for new split
        if st.button("Add Split"):
            st.session_state[f"splits_{service}"].append({
                'id': row[id_col],
                'amount': 0,
                'category': '',
                'tag': ''
            })
            st.rerun()

        # Save and Cancel buttons
        col_save, col_cancel, col_cancel_split = st.columns(3)

        with col_save:
            if st.button("Save Splits"):
                # Validate total amount
                total_split_amount = sum(split.get('amount', 0) for split in st.session_state[f"splits_{service}"])
                if abs(total_split_amount - row[amount_col]) != 0:
                    st.error(f"Total split amount ({total_split_amount}) does not match transaction amount ({row[amount_col]})")
                else:
                    self.split_transactions_service.split_transaction(
                        transaction_id=row[id_col],
                        service=service,
                        splits=st.session_state[f"splits_{service}"]
                    )
                    # Update the original transaction to category 'Ignore' and tag 'splitted'
                    self.transactions_service.update_tagging_by_id(
                        id_=row[id_col],
                        category=NonExpensesCategories.IGNORE.value,
                        tag="splitted",
                        service=service
                    )
                    # Clear session state
                    del st.session_state[f"splits_{service}"]
                    st.success("Transaction split successfully!")
                    st.rerun()

        with col_cancel:
            if st.button("Cancel"):
                # Clear session state
                if f"splits_{service}" in st.session_state:
                    del st.session_state[f"splits_{service}"]
                st.rerun()

        with col_cancel_split:
            activate_button = row[category_col] == NonExpensesCategories.IGNORE.value and row[tag_col] == "splitted"
            if st.button("Cancel Split", disabled=not activate_button):
                # Delete all splits and reset original transaction's category and tag to None
                self.split_transactions_service.cancel_split(row[id_col], service)
                self.transactions_service.update_tagging_by_id(
                    id_=row[id_col],
                    category=None,
                    tag=None,
                    service=service
                )
                if f"splits_{service}" in st.session_state:
                    del st.session_state[f"splits_{service}"]
                st.success("Split cancelled and transaction restored.")
                st.rerun()
