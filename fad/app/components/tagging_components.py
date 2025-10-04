from time import sleep
from typing import List

import pandas as pd
import streamlit as st

from fad.app.naming_conventions import NonExpensesCategories
from fad.app.naming_conventions import (
    RuleFields,
    TransactionsTableFields,
    TaggingRulesTableFields
)
from fad.app.services.split_transactions_service import SplitTransactionsService
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.services.transactions_service import TransactionsService
from fad.app.utils.widgets import PandasFilterWidgets
from fad.app.utils.streamlit import clear_session_state


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
                sleep(1)
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
                sleep(1)
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
                sleep(1)
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
                        sleep(1)
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
                sleep(1)
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
                sleep(1)
                st.rerun()
            else:
                st.error("Failed to delete some tags.")
        if st.button('No', key=f'cancel_delete_{category}_tags'):
            st.rerun()


# TODO: in edit transactions, add an option to cancel splits cleaning up the split entries and resetting the original transaction's category and tag to None
class TransactionsTaggingComponent:
    """
    Component for manual transaction tagging, bulk editing, and transaction data editing.

    This component provides:
    1. Manual transaction tagging with rule creation integration
    2. Bulk tagging operations
    3. Transaction data editing
    """

    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.transactions_service = TransactionsService()
        self.split_transactions_service = SplitTransactionsService()
        self.categories_tags_service = CategoriesTagsService()
        self.rules_service = TaggingRulesService()
        self.auto_tagger_rules_component = RuleBasedTaggingComponent(key_suffix)
        self.categories_and_tags = self.categories_tags_service.get_categories_and_tags()

    def render_tagging_page(self) -> None:
        """
        Render the transactions tagging component UI.

        Creates tabs for different aspects of transaction tagging:
        - Manual Tagging: Individual transaction tagging with rule creation
        - Bulk Tagging: Multiple transaction operations
        - Edit Transactions: Transaction data editing
        """
        st.subheader("Transactions Tagging & Editing")
        st.markdown(
            "Tag transactions manually, perform bulk operations, and edit transaction data. "
            "Create intelligent rules while tagging to automate future similar transactions."
        )

        manual_tab, edit_tab = st.tabs([
            "Tag",
            "Edit"
        ])

        with manual_tab:
            self.render_transactions_tagging()

        with edit_tab:
            self.render_transaction_editing()

    def render_transactions_tagging(self) -> None:
        """Render the manual tagging interface."""
        st.markdown(
            "Select transactions to tag or create rules for automatic tagging."
        )

        # Service selection
        service = st.pills(
            "Select transaction type:",
            options=["credit_card", "bank"],
            default="credit_card",
            selection_mode="single",
            format_func=lambda x: x.replace('_', ' ').title(),
            key="manual_tagging_service_selector"
        )

        # auto tagger rules setup
        with st.expander("🤖 Auto Tagger Rules Overview", expanded=False):
            self.auto_tagger_rules_component.render()

        if st.checkbox("Show already tagged transactions for re-tagging", key="manual_show_tagged"):
            all_transactions = self.transactions_service.get_all_transactions(service)
            if all_transactions.empty:
                st.info("No transactions found.")
            else:
                self.render_transactions_table_for_tagging(all_transactions, key_suffix="manual_tagging_tagged")
        else:
            untagged_transactions = self.transactions_service.get_untagged_transactions(service)
            if untagged_transactions.empty:
                st.info("🎉 No untagged transactions found. All transactions have been categorized!")
                st.info("Use the checkbox above to view and edit already tagged transactions.")
            else:
                self.render_transactions_table_for_tagging(untagged_transactions, key_suffix="manual_tagging_untagged")

    def render_transactions_table_for_tagging(self, transactions: pd.DataFrame, key_suffix: str) -> None:
        """
        Render transaction filtering and selection interface for tagging.

        Parameters
        ----------
        transactions : pd.DataFrame
            The transactions to display and filter.
        key_suffix : str
            A suffix to ensure unique Streamlit keys.

        Returns
        -------
        None
        """
        info_container = st.container()
        show_filters = st.checkbox("Show Filters", key=f"show_filters_{self.key_suffix}_{key_suffix}", value=False)
        if show_filters:
            data_col, filter_col = st.columns([0.7, 0.3], border=True)
        else:
            data_col = st.container(border=True)
            filter_col = None

        if filter_col is None:
            filtered_transactions = transactions
        else:
            with filter_col:
                # Create filter widgets
                widgets_map = {
                    TransactionsTableFields.AMOUNT.value: 'number_range',
                    TransactionsTableFields.DATE.value: 'date_range',
                    TransactionsTableFields.PROVIDER.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
                    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
                }
                df_filter = PandasFilterWidgets(transactions, widgets_map, key_suffix=f"{self.key_suffix}_{key_suffix}")
                df_filter.display_widgets()
                filtered_transactions = df_filter.filter_df()

        info_container.info(f"Found {len(filtered_transactions)} transactions")

        with data_col:
            if filtered_transactions.empty:
                st.info("No transactions match the current filters.")
                return

            # Display transactions with selection
            columns_order = self.transactions_service.get_table_columns_for_display()

            filtered_transactions = filtered_transactions.sort_values([TransactionsTableFields.DATE.value], ascending=False)
            selections = st.dataframe(
                filtered_transactions,
                key=f'manual_dataframe_{self.key_suffix}_{key_suffix}',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='multi-row',
                use_container_width=True
            )

            # Handle selected transaction
            indices = selections['selection']['rows']
            data_to_tag = filtered_transactions.iloc[indices]
            self.render_tagging_settings_panel(data_to_tag, key_suffix=key_suffix)

    def render_tagging_settings_panel(self, transactions: pd.DataFrame | pd.Series, key_suffix: str) -> None:
        """
        Render the tagging settings panel for selected transactions, allowing manual tagging, removal of tags, or
        splitting.

        Parameters
        ----------
        transactions : pd.DataFrame | pd.Series
            The transaction(s) to be tagged.
        key_suffix : str
            A suffix to ensure unique Streamlit keys.
        """
        st.markdown("---")
        if len(transactions) == 0:
            st.info("Select at least one transaction to start editing.")
            return

        # Get current category and tag
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        id_col = TransactionsTableFields.ID.value
        desc_col = TransactionsTableFields.DESCRIPTION.value
        amount_col = TransactionsTableFields.AMOUNT.value
        provider_col = TransactionsTableFields.PROVIDER.value

        transactions = pd.DataFrame(transactions)  # Ensure it's a DataFrame

        # split transaction checks and ui rendering if needed
        has_splits = [self.split_transactions_service.has_splits(transaction[id_col]) for _, transaction in transactions.iterrows()]
        if len(transactions) > 1 and any(has_splits):
            # multiple transactions with at least one split selected
            splitted_transactions = transactions[has_splits]
            error_txt = ", ".join([f"{t[TransactionsTableFields.DESCRIPTION.value]} (id: {t[id_col]})" for _, t in splitted_transactions.iterrows()])
            st.error(f"Transactions {error_txt} have been split. You cannot bulk tag them with other transactions. To edit their tagging, please select them individually.")
            return
        elif any(has_splits) or st.session_state.get(f"splits_{self.key_suffix}_{key_suffix}", [{}])[0].get(id_col) == transactions.iloc[0][id_col] or st.session_state.get(f"split_transaction_{transactions.iloc[0].get(id_col)}", False):
            # single transaction with splits selected or split tagging in progress or split button clicked
            self._render_split_transaction_ui(transactions.iloc[0], key_suffix=key_suffix)
            return

        col1, col2, col3 = st.columns(3)
        for _, transaction in transactions.iterrows():
            with col1:
                st.write(f"**Description:** {transaction[desc_col]}")
            with col2:
                st.write(f"**Amount:** {transaction[amount_col]}")
            with col3:
                st.write(f"**Provider:** {transaction[provider_col]}")

        # Warn if multiple transactions have different existing categories/tags
        if len(transactions) > 1:
            curr_categories = transactions[category_col].unique()
            curr_tags = transactions[tag_col].unique()
            if len(curr_categories) > 1 or len(curr_tags) > 1:
                st.warning("Selected transactions have different existing categories/tags. When you save, the selected category/tag will be applied to all selected transactions.")

        # Tagging UI
        col_cat, col_tag, col_save, col_remove, col_split = st.columns([0.2, 0.2, 0.2, 0.2, 0.2])
        current_category = transactions.iloc[0].get(category_col)
        current_tag = transactions.iloc[0].get(tag_col)

        with col_cat:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                "Category",
                options=[None] + categories,
                index=categories.index(current_category) + 1 if current_category in categories else 0,
                format_func=lambda x: "No category" if x is None else x,
                key=f'manual_category_{transactions[id_col].tolist()}'  # use list of ids for multi-selection
            )

        with col_tag:
            tags = self.categories_and_tags.get(category, []) if category else []
            tag = st.selectbox(
                "Tag",
                options=[None] + tags,
                index=tags.index(current_tag) + 1 if current_tag in tags and category else 0,
                format_func=lambda x: "No tag" if x is None else x,
                key=f'manual_tag_{transactions[id_col].tolist()}'  # use list of ids for multi-selection
            )

        with col_save:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Save', key=f'save_manual_{transactions[id_col].tolist()}'):
                if category and tag:
                    for _, transaction in transactions.iterrows():
                        self.transactions_service.update_tagging_by_id(
                            transaction[id_col], category, tag
                        )
                    self._clear_data_and_filters_session_state(key_suffix)
                    st.success("Transaction tagged successfully!")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Please select both category and tag.")

        with col_remove:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Remove Tags', key=f'remove_tags_{transactions[id_col].tolist()}', type="secondary", disabled=any(transactions[category_col].isnull()) and all(transactions[tag_col].isnull())):
                for _, transaction in transactions.iterrows():
                    self.transactions_service.update_tagging_by_id(
                        transaction[id_col], None, None
                    )
                self._clear_data_and_filters_session_state(key_suffix)
                st.success("Transaction tags removed!")
                sleep(1)
                st.rerun()

        with col_split:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button('Split Transaction', key=f'split_transaction_{transactions.iloc[0].get(id_col)}', disabled=len(transactions) > 1, help="To split a transaction, select only one transaction at a time.")

    @st.fragment
    def _render_split_transaction_ui(self, transaction: pd.Series, key_suffix: str = ''):
        """
        A fragment to split a transaction into multiple parts. The fragment displays a form for adding
        multiple splits with amount, category, and tag, and validates that the total amount matches
        the original transaction amount.

        Parameters
        ----------
        transaction : pd.Series
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
        existing_splits = self.split_transactions_service.get_splits_for_transaction(transaction[id_col])

        # Initialize session state for splits if not already initialized
        if f"splits_{self.key_suffix}_{key_suffix}" in st.session_state:
            # Ensure the session state split is of the same data row - update it if not
            if transaction[id_col] != st.session_state[f"splits_{self.key_suffix}_{key_suffix}"][0].get('id'):
                st.session_state[f"splits_{self.key_suffix}_{key_suffix}"] = [
                    {
                        'id': transaction[id_col],
                        'amount': transaction[amount_col],
                        'category': '',
                        'tag': ''
                    }
                ]
        else:
            if not existing_splits.empty:
                # Convert existing splits to list of dictionaries
                st.session_state[f"splits_{self.key_suffix}_{key_suffix}"] = existing_splits.to_dict('records')
            else:
                # Start with one empty split with the full amount
                st.session_state[f"splits_{self.key_suffix}_{key_suffix}"] = [
                    {
                        'id': transaction[id_col],
                        'amount': transaction[amount_col],
                        'category': '',
                        'tag': ''
                    }
                ]

        # Display transaction details
        st.info("⚠️ The total amount of all splits must equal the original transaction amount.")
        st.write(f"Total Amount: {transaction[amount_col]}")

        # Display current splits
        st.write("Splits:")

        # Display each split
        for i, split in enumerate(st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]):
            col1, col2, col3, col4 = st.columns([0.2, 0.3, 0.3, 0.2])

            with col1:
                split['amount'] = st.number_input(
                    "Amount",
                    value=float(split.get('amount', 0)),
                    key=f"split_amount_{i}_{self.key_suffix}_{key_suffix}",
                )

            with col2:
                categories = list(self.categories_tags_service.categories_and_tags.keys())
                split['category'] = st.selectbox(
                    "Category",
                    options=categories,
                    index=categories.index(split.get('category')) if split.get('category') in categories else None,
                    key=f"split_category_{i}_{self.key_suffix}_{key_suffix}"
                )

            with col3:
                tags = self.categories_tags_service.categories_and_tags.get(split.get('category', ''), [])
                split['tag'] = st.selectbox(
                    "Tag",
                    options=tags,
                    index=tags.index(split.get('tag')) if split.get('tag') in tags and split.get('tag') else None,
                    key=f"split_tag_{i}_{self.key_suffix}_{key_suffix}"
                )

            with col4:
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
                disable = len(st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]) == 1
                if st.button("Remove", key=f"remove_split_{i}_{self.key_suffix}_{key_suffix}", disabled=disable):
                    st.session_state[f"splits_{self.key_suffix}_{key_suffix}"].pop(i)
                    st.rerun(scope="fragment")

        # Add button for new split
        if st.button("Add Split"):
            st.session_state[f"splits_{self.key_suffix}_{key_suffix}"].append({
                'id': transaction[id_col],
                'amount': 0,
                'category': '',
                'tag': ''
            })
            st.rerun(scope="fragment")

        # Save and Cancel buttons
        col_save, col_cancel, col_cancel_split = st.columns(3)

        with col_save:
            if st.button("Save Splits"):
                # Validate total amount
                total_split_amount = sum(split.get('amount', 0) for split in st.session_state[f"splits_{self.key_suffix}_{key_suffix}"])
                if abs(total_split_amount - transaction[amount_col]) > 1e-6:  # Allow small floating point errors
                    st.error(f"Total split amount ({total_split_amount}) does not match transaction amount ({transaction[amount_col]})")
                else:
                    self.split_transactions_service.split_transaction(
                        transaction_id=transaction[id_col],
                        splits=st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]
                    )
                    # Update the original transaction to category 'Ignore' and tag 'splitted'
                    self.transactions_service.update_tagging_by_id(
                        id_=transaction[id_col],
                        category=NonExpensesCategories.IGNORE.value,
                        tag="splitted",
                    )
                    # Clear session state
                    del st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]
                    self._clear_data_and_filters_session_state(key_suffix)
                    st.success("Transaction split successfully!")
                    sleep(1)
                    st.rerun()

        with col_cancel:
            if st.button("Cancel"):
                # Clear session state
                if f"splits_{self.key_suffix}_{key_suffix}" in st.session_state:
                    del st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]
                st.rerun()

        with col_cancel_split:
            activate_button = transaction[category_col] == NonExpensesCategories.IGNORE.value and transaction[tag_col] == "splitted"
            if st.button("Cancel Split", disabled=not activate_button):
                # Delete all splits and reset original transaction's category and tag to None
                self.split_transactions_service.cancel_split(transaction[id_col])
                self.transactions_service.update_tagging_by_id(
                    id_=transaction[id_col],
                    category=None,
                    tag=None,
                )
                if f"splits_{self.key_suffix}_{key_suffix}" in st.session_state:
                    del st.session_state[f"splits_{self.key_suffix}_{key_suffix}"]
                self._clear_data_and_filters_session_state(key_suffix)
                st.success("Split cancelled and transaction restored.")
                sleep(1)
                st.rerun()

    def _clear_data_and_filters_session_state(self, key_suffix: str) -> None:
        """Clear session state of displayed data to make sure updated data is shown."""
        df_filter = st.session_state[f"{PandasFilterWidgets.BASE_STREAMLIT_KEY}_{self.key_suffix}_{key_suffix}"]
        df_filter.delete_session_state()

    def render_transaction_editing(self) -> None:
        """Render transaction data editing interface."""
        st.markdown("Select a transaction to edit its details (description, amount, provider, etc.)")

        self.create_new_transaction_button()

        # Service selection
        service = st.pills(
            "Select transaction type:",
            options=["credit_card", "bank"],
            default="credit_card",
            format_func=lambda x: x.replace('_', ' ').title(),
            key="edit_service_selector"
        )

        # Get all transactions for editing
        all_transactions = self.transactions_service.get_all_transactions(service)

        if all_transactions.empty:
            st.info("No transactions found.")
            return

        # Filter interface using comprehensive widgets
        info_container = st.container()
        show_filters = st.checkbox("Show Filters", key=f"show_filters_{self.key_suffix}_edit", value=True)
        if show_filters:
            data_col, filter_col = st.columns([0.7, 0.3], border=True)
        else:
            data_col = st.container(border=True)
            filter_col = None

        if filter_col is None:
            filtered_transactions = all_transactions
        else:
            with filter_col:
                st.markdown("**Filter Transactions**")

                # Create filter widgets for editing operations
                widgets_map = {
                    TransactionsTableFields.AMOUNT.value: 'number_range',
                    TransactionsTableFields.DATE.value: 'date_range',
                    TransactionsTableFields.PROVIDER.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
                    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
                    TransactionsTableFields.CATEGORY.value: 'multiselect',
                    TransactionsTableFields.TAG.value: 'multiselect',
                }
                df_filter = PandasFilterWidgets(all_transactions, widgets_map, key_suffix=f"{self.key_suffix}_{service}")
                df_filter.display_widgets()
                filtered_transactions = df_filter.filter_df()

        info_container.info(f"Found {len(filtered_transactions)} transactions")

        with data_col:
            if filtered_transactions.empty:
                st.info("No transactions match the current filters.")
                return

            # Transaction selection
            columns_order = self.transactions_service.get_table_columns_for_display()

            filtered_transactions = filtered_transactions.sort_values([TransactionsTableFields.DATE.value], ascending=False)
            selections = st.dataframe(
                filtered_transactions,
                key=f'{service}_edit_dataframe',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
                height=400,
                use_container_width=True
            )

            # Handle selected transaction for editing
            indices = selections['selection']['rows']
            if indices:
                idx = indices[0]
                selected_transaction = filtered_transactions.iloc[idx]
                self._render_transaction_editor(selected_transaction)

    def create_new_transaction_button(self) -> None:
        """Render the button to create a new transaction."""
        if st.button("➕ Create New Transaction", key=f"create_btn_new_transaction_{self.key_suffix}"):
            self._render_create_transaction_dialog()

    @st.dialog("Create New Transaction")
    def _render_create_transaction_dialog(self) -> None:
        """Render the dialog to create a new transaction."""
        service = st.selectbox("Type:", options=["cash"], index=0, format_func=lambda x: x.replace('_', ' ').title(), key=f"type_new_transaction_{self.key_suffix}")
        date = st.date_input("Date:", key=f"new_transaction_date_{self.key_suffix}", value=pd.Timestamp.now().date())
        description = st.text_input("Description:", key=f"description_new_transaction_{self.key_suffix}")
        amount = st.number_input("Amount (negative for expenses):", format="%.2f", key=f"amount_new_transaction_{self.key_suffix}")
        account_name = st.text_input("Account Name:", key=f"account_name_new_transaction_{self.key_suffix}")

        if st.button("Save Transaction", key=f"save_btn_new_transaction_{self.key_suffix}"):
            if not description or amount == 0 or not account_name:
                st.error("Please fill in all required fields (Description, Amount, Account Name).")
                return

            new_transaction = {
                TransactionsTableFields.DATE.value: pd.Timestamp(date),
                TransactionsTableFields.DESCRIPTION.value: description,
                TransactionsTableFields.AMOUNT.value: amount,
                TransactionsTableFields.ACCOUNT_NAME.value: account_name,
                TransactionsTableFields.PROVIDER.value: None,
                TransactionsTableFields.ACCOUNT_NUMBER.value: None,
                TransactionsTableFields.CATEGORY.value: None,
                TransactionsTableFields.TAG.value: None,
            }

            success = self.transactions_service.add_transaction(new_transaction, service)

            if success:
                st.success("✅ Transaction created successfully!")
                clear_session_state(ends_with=[f"_new_transaction_{self.key_suffix}"])
                sleep(1)  # slight delay for better UX
                st.rerun()
            else:
                st.error("❌ Failed to create transaction. Please try again.")

        if st.button("Cancel", key="cancel_create_transaction_btn"):
            clear_session_state(ends_with=[f"_new_transaction_{self.key_suffix}"])
            st.rerun()

    def _render_transaction_editor(self, transaction: pd.Series) -> None:
        """Render the transaction editor interface."""
        st.markdown("---")
        st.markdown("#### Edit Transaction Details")

        id_col = TransactionsTableFields.ID.value
        transaction_id = transaction[id_col]

        with st.container(border=True):
            self._transaction_editor_fragment(transaction, transaction_id)

    @st.fragment
    def _transaction_editor_fragment(self, transaction: pd.Series, transaction_id: str) -> None:
        """Fragment for transaction editing form."""
        col1, col2 = st.columns(2)

        with col1:
            # Editable fields
            new_description = st.text_input(
                "Description:",
                value=transaction[TransactionsTableFields.DESCRIPTION.value],
                key=f"edit_desc_{transaction_id}"
            )

            new_amount = st.number_input(
                "Amount:",
                value=float(transaction[TransactionsTableFields.AMOUNT.value]),
                format="%.2f",
                key=f"edit_amount_{transaction_id}"
            )

            new_provider = st.text_input(
                "Provider:",
                value=transaction[TransactionsTableFields.PROVIDER.value] or "",
                key=f"edit_provider_{transaction_id}"
            )

        with col2:
            # Category and tag editing
            categories = list(self.categories_and_tags.keys())
            current_category = transaction.get(TransactionsTableFields.CATEGORY.value)

            new_category = st.selectbox(
                "Category:",
                options=[None] + categories,
                index=categories.index(current_category) + 1 if current_category in categories else 0,
                format_func=lambda x: "No category" if x is None else x,
                key=f"edit_category_{transaction_id}"
            )

            tags = self.categories_and_tags.get(new_category, []) if new_category else []
            current_tag = transaction.get(TransactionsTableFields.TAG.value)

            new_tag = st.selectbox(
                "Tag:",
                options=[None] + tags,
                index=tags.index(current_tag) + 1 if current_tag in tags else 0,
                format_func=lambda x: "No tag" if x is None else x,
                key=f"edit_tag_{transaction_id}"
            )

        # Save button
        if st.button("💾 Save Changes", type="primary", key=f"save_transaction_{transaction_id}"):
            # Update transaction
            updates = {
                TransactionsTableFields.DESCRIPTION.value: new_description,
                TransactionsTableFields.AMOUNT.value: new_amount,
                TransactionsTableFields.PROVIDER.value: new_provider,
                TransactionsTableFields.CATEGORY.value: new_category,
                TransactionsTableFields.TAG.value: new_tag,
            }

            success = self.transactions_service.update_transaction_by_id(transaction_id, updates)

            if success:
                st.success("✅ Transaction updated successfully!")
                sleep(1)
                st.rerun()
            else:
                st.error("❌ Failed to update transaction")


class RuleBasedTaggingComponent:
    """
    Component for rule-based transaction tagging management.

    This component provides:
    1. Rule management (create, edit, delete, prioritize)
    2. Rule testing and preview
    3. Rule application to transactions
    """

    def __init__(self, key_suffix: str):
        self.key_suffix = key_suffix
        self.rules_service = TaggingRulesService()
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def render(self) -> None:
        """
        Render the rule-based tagging component UI.

        Creates tabs for different aspects of rule management:
        - Rule Management: View, edit, delete, and prioritize rules
        - Rule Testing: Test rules against transactions
        - Apply Rules: Apply rules to untagged transactions
        """
        st.info(
            "Create and manage intelligent rules that automatically tag transactions based on description, amount, provider, and other fields. "
            "Rules use operators like 'contains', 'greater than', etc., to match transactions."
        )

        self.render_existing_rules()
        if st.button("➕ Create New Rule", key=f"create_new_rule_btn_{self.key_suffix}", type="secondary"):
            self.render_rule_creation_interface()

    def render_existing_rules(self) -> None:
        """Render the rule management interface."""
        st.markdown("### Edit Existing Rules")
        st.markdown("Manage your tagging rules: view, edit, delete, and prioritize them.")

        # Get rules
        rules_df = self.rules_service.get_all_rules(active_only=False)

        if rules_df.empty:
            st.info("No rules found. Create some rules in the Transaction Tagging tab!")
            return

        # Rules table
        st.markdown("#### All Rules")

        # Display rules table
        display_columns = [
            TaggingRulesTableFields.NAME.value,
            TaggingRulesTableFields.CATEGORY.value,
            TaggingRulesTableFields.TAG.value,
            TaggingRulesTableFields.PRIORITY.value,
            TaggingRulesTableFields.IS_ACTIVE.value
        ]
        selections = st.dataframe(
            rules_df[display_columns],
            key=f"rules_management_table_{self.key_suffix}",
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True,
            use_container_width=True
        )

        # Rule editor
        selected_rows = selections['selection']['rows']
        if selected_rows:
            selected_rule_id = rules_df.iloc[selected_rows[0]]['id']
            with st.container(border=True, key=f"rule_editor_{selected_rule_id}_{self.key_suffix}"):
                self._render_rule_editor(selected_rule_id)
        else:
            st.info("Please select a rule from the table to edit it.")

    def _render_rule_editor(self, rule_id: int) -> None:
        """Render the rule editor interface."""
        st.markdown("#### Edit Rule")

        rule = self.rules_service.get_rule_by_id(rule_id)
        if rule is None:
            st.error("Rule not found!")
            return

        # Initialize conditions in session state for editing
        conditions_key = f"edit_rule_conditions_{rule_id}"
        if conditions_key not in st.session_state:
            st.session_state[conditions_key] = rule['conditions'].copy()

        self._rule_editor_fragment(rule, rule_id, conditions_key)

    @st.fragment
    def _rule_editor_fragment(self, rule: dict, rule_id: int, conditions_key: str) -> None:
        """Fragment for rule editing form."""
        new_name = st.text_input("Rule Name:", value=rule['name'], key=f"edit_name_{rule_id}_{self.key_suffix}")

        save_col, delete_col = st.columns(2)
        with save_col:
            categories = list(self.categories_and_tags.keys())
            new_category = st.selectbox(
                "Category:",
                options=categories,
                index=categories.index(rule['category']) if rule['category'] in categories else 0,
                key=f"edit_category_{rule_id}_{self.key_suffix}"
            )

        with delete_col:
            tags = self.categories_and_tags.get(new_category, [])
            new_tag = st.selectbox(
                "Tag:",
                options=tags,
                index=tags.index(rule['tag']) if rule['tag'] in tags else 0,
                key=f"edit_tag_{rule_id}_{self.key_suffix}"
            )

        new_priority = st.number_input("Priority:", value=int(rule['priority']), min_value=1, max_value=10, key=f"priority_{rule_id}_{self.key_suffix}")
        new_is_active = st.checkbox("Active", value=bool(rule['is_active']), key=f"active_{rule_id}_{self.key_suffix}")

        # Editable conditions section
        st.markdown("**Conditions (all must match):**")

        # Display existing conditions with edit capability
        conditions = st.session_state[conditions_key]
        for i, condition in enumerate(conditions):
            self._render_condition_editor(i, condition, conditions_key, conditions)

        enable_more_conditions = [e.value for e in RuleFields if e.value not in [c['field'] for c in conditions]]
        if st.button("➕ Add Condition", key=f"add_condition_{rule_id}_{self.key_suffix}", disabled=not enable_more_conditions):
                st.session_state[conditions_key].append({
                    'field': enable_more_conditions[0],
                    'operator': self.rules_service.get_operators_for_field(enable_more_conditions[0])[0],
                    'value': ''
                })
                st.rerun()

        # Action buttons
        save_col, delete_col, test_col, _ = st.columns([1, 1, 1, 5])
        with save_col:
            if st.button("💾 Save Changes", key=f"save_rule_{rule_id}_{self.key_suffix}", type="primary"):
                # Validate conditions
                conditions_errors = self.rules_service.validate_conditions(st.session_state[conditions_key])
                if conditions_errors:
                    st.error(f"❌ Invalid conditions found:\n{conditions_errors}")
                    return

                # Update rule with new conditions
                success = self.rules_service.update_rule(
                    rule_id=rule_id,
                    name=new_name,
                    category=new_category,
                    tag=new_tag,
                    priority=new_priority,
                    is_active=new_is_active,
                    conditions=st.session_state[conditions_key]
                )
                if success:
                    st.success("✅ Rule updated successfully!")
                    # Clear the session state for conditions
                    del st.session_state[conditions_key]
                    sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Failed to update rule")

        with delete_col:
            if st.button("🗑️ Delete Rule", key=f"delete_rule_{rule_id}_{self.key_suffix}", type="secondary"):
                success = self.rules_service.delete_rule(rule_id)
                if success:
                    st.success("✅ Rule deleted successfully!")
                    # Clear the session state for conditions
                    if conditions_key in st.session_state:
                        del st.session_state[conditions_key]
                    sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Failed to delete rule")

        with test_col:
            if st.button("🧪 Test Rule", key=f"test_rule_{rule_id}_{self.key_suffix}"):
                # Test with current conditions from session state
                count, test_results = self.rules_service.test_rule_against_transactions(
                    conditions=st.session_state[conditions_key],
                )
            else:
                test_results = None
                count = 0

        if test_results is not None:
            st.info(f"Rule would match {count} transactions:")
            if count > 0:
                st.data_editor(test_results, disabled=True, column_order=self.transactions_service.get_table_columns_for_display(), hide_index=True, use_container_width=True)

    @st.dialog("Create New Rule", width="large")
    def render_rule_creation_interface(self) -> None:
        """
        Render interface for creating rules based on a transaction.
        This method is called from TransactionsTaggingComponent.
        """
        st.markdown("Create a rule to automatically tag similar transactions in the future.")

        # Rule name
        rule_name = st.text_input(
            "Rule Name",
            placeholder="Enter Rule Name",
            key=f"new_rule_name_input_{self.key_suffix}"
        )

        # Rule conditions builder
        st.markdown("**Conditions (all must match):**")

        # Display existing conditions
        conditions_key = f"new_rule_conditions"
        conditions = st.session_state.setdefault(conditions_key, [])
        for i, condition in enumerate(conditions):
            self._render_condition_editor(i, condition, conditions_key, conditions)

        enable_more_conditions = [e.value for e in RuleFields if e.value not in [c['field'] for c in conditions]]
        if st.button("➕ Add Condition", key=f"add_rule_condition_{self.key_suffix}", disabled=not enable_more_conditions):
            st.session_state[conditions_key].append({
                'field': enable_more_conditions[0],
                'operator': self.rules_service.get_operators_for_field(enable_more_conditions[0])[0],
                'value': ''
            })
            st.rerun(scope="fragment")

        # Category and tag selection for rule
        col_cat, col_tag = st.columns(2)

        with col_cat:
            categories = list(self.categories_and_tags.keys())
            rule_category = st.selectbox(
                "Category for rule:",
                options=categories,
                key=f'rule_category_{self.key_suffix}'
            )

        with col_tag:
            tags = self.categories_and_tags.get(rule_category, []) if rule_category else []
            rule_tag = st.selectbox(
                "Tag for rule:",
                options=tags,
                key=f'rule_tag_{self.key_suffix}'
            )

        col_create, col_test, _ = st.columns([1, 1, 3])

        with col_create:
            empty_conditions = len(conditions) == 0 or any([c['value'] == '' for c in conditions])
            dont_allow_buttons = not (rule_name and not empty_conditions and rule_category and rule_tag)
            dont_allow_txt = "Please provide rule name, at least one condition, category, and tag."
            if st.button("🚀 Create Rule", key=f"create_rule_{self.key_suffix}", disabled=dont_allow_buttons, help=dont_allow_txt):
                conditions_errors = self.rules_service.validate_conditions(conditions)
                if conditions_errors:
                    st.error(f"❌ Invalid conditions found:\n{conditions_errors}")
                    return

                rule_id = self.rules_service.add_rule(
                    name=rule_name,
                    conditions=conditions,
                    category=rule_category,
                    tag=rule_tag,
                )
                st.success(f"✅ Rule created successfully! (ID: {rule_id})")
                # Clear the conditions
                st.session_state[conditions_key] = []

                total_tagged = self.rules_service.apply_rules()

                if total_tagged > 0:
                    st.success(f"✅ Tagged {total_tagged} transactions total!")
                else:
                    st.info("No transactions were tagged. All may already be categorized or no rules matched.")
                sleep(1)
                st.rerun()

        with col_test:
            if st.button("🧪 Test Rule", key=f"test_new_rule_{self.key_suffix}", disabled=dont_allow_buttons, help=dont_allow_txt):
                count, matched_transactions = self.rules_service.test_rule_against_transactions(
                    conditions=conditions,
                )
            else:
                matched_transactions = None
                count = 0

        if matched_transactions is not None:
            st.info(f"Rule would match {count} transactions:")
            if count > 0:
                st.data_editor(matched_transactions, disabled=True, column_order=self.transactions_service.get_table_columns_for_display(), hide_index=True, use_container_width=True)

    def _render_condition_editor(self, index: int, condition: dict, conditions_key: str, conditions: List[dict]) -> None:
        """Render a single condition editor."""
        col1, col2, col3, col4 = st.columns([0.25, 0.25, 0.4, 0.1])

        taken_fields = [
            st.session_state[f"field_{conditions_key}_{i}_{self.key_suffix}"]
            if f"field_{conditions_key}_{i}_{self.key_suffix}" in st.session_state
            else c['field']
            for i, c in enumerate(conditions)
            if i != index
        ]

        with col1:
            available_fields = [e.value for e in RuleFields if e.value not in taken_fields]
            field = st.selectbox(
                f"Field {index + 1}",
                options=available_fields,
                index=available_fields.index(st.session_state.get(f"field_{conditions_key}_{index}_{self.key_suffix}", condition['field'])),
                key=f"field_{conditions_key}_{index}_{self.key_suffix}"
            )

        with col2:
            # Get available operators based on field type
            available_operators = self.rules_service.get_operators_for_field(field)

            # Ensure current operator is valid for the field, otherwise use first available
            current_operator = condition['operator']
            if current_operator not in available_operators:
                current_operator = available_operators[0]

            default = st.session_state.get(f"operator_{conditions_key}_{index}_{self.key_suffix}", current_operator)
            operator = st.selectbox(
                f"Operator {index + 1}",
                options=available_operators,
                index=available_operators.index(default) if default in available_operators else 0,
                key=f"operator_{conditions_key}_{index}_{self.key_suffix}"
            )

        with col3:
            if field == RuleFields.SERVICE.value:
                value = st.selectbox(
                    f"Value {index + 1}",
                    options=["credit_card", "bank"],
                    format_func=lambda x: x.replace('_', ' ').title(),
                    key=f"edit_value_{conditions_key}_{index}_{self.key_suffix}"
                )
            elif field == RuleFields.PROVIDER.value:
                service_condition_value = [
                    st.session_state.get(f"edit_value_{conditions_key}_{i}_{self.key_suffix}", c['value']) for i, c in
                    enumerate(conditions) if st.session_state.get(f"field_{conditions_key}_{i}_{self.key_suffix}") == RuleFields.SERVICE.value or c['field'] == RuleFields.SERVICE.value]
                if service_condition_value:
                    service = service_condition_value[0]
                    if service not in ["credit_card", "bank"]:
                        # in case the index of the service condition is greater than the provider condition and the service default value is not set yet (defaults to credit_card)
                        service = "credit_card"
                    providers = self.transactions_service.get_providers_for_service(service)
                else:
                    providers = self.transactions_service.get_all_providers()
                value = st.selectbox(
                    f"Value {index + 1}",
                    options=providers,
                    key=f"edit_value_{conditions_key}_{index}_{self.key_suffix}"
                )
            elif field == RuleFields.AMOUNT.value:
                value = st.number_input(
                    f"Value {index + 1}",
                    format="%.2f",
                    key=f"edit_value_{conditions_key}_{index}_{self.key_suffix}"
                )
            else:
                value = st.text_input(
                    f"Value {index + 1}",
                    key=f"edit_value_{conditions_key}_{index}_{self.key_suffix}"
                )

        with col4:
            st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
            if st.button("🗑️", key=f"delete_{conditions_key}_{index}_{self.key_suffix}"):
                st.session_state[conditions_key].pop(index)
                st.rerun(scope="fragment")

        # Update the condition in session state
        st.session_state[conditions_key][index] = {
            'field': field,
            'operator': operator,
            'value': value
        }

        if field != condition['field']:
            # If field changed, rerun to update previous condition editors
            st.rerun(scope="fragment")
