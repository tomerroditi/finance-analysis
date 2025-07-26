from typing import Literal, List
import pandas as pd
import streamlit as st

from fad.app.naming_conventions import TransactionsTableFields
from fad.app.services.split_transactions_service import SplitTransactionsService
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.services.transactions_service import TransactionsService
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.app.utils.widgets import PandasFilterWidgets
from fad.app.components.rule_based_tagging_components import RuleBasedTaggingComponent


class TransactionsTaggingComponent:
    """
    Component for manual transaction tagging, bulk editing, and transaction data editing.

    This component provides:
    1. Manual transaction tagging with rule creation integration
    2. Bulk tagging operations
    3. Transaction data editing
    """

    def __init__(self):
        self.transactions_service = TransactionsService()
        self.split_transactions_service = SplitTransactionsService()
        self.categories_tags_service = CategoriesTagsService()
        self.rules_service = TaggingRulesService()
        self.rule_component = RuleBasedTaggingComponent()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def render(self) -> None:
        """
        Render the transactions tagging component UI.

        Creates tabs for different aspects of transaction tagging:
        - Manual Tagging: Individual transaction tagging with rule creation
        - Bulk Tagging: Multiple transaction operations
        - Edit Transactions: Transaction data editing
        """
        st.subheader("Transaction Tagging & Editing")
        st.markdown(
            "Tag transactions manually, perform bulk operations, and edit transaction data. "
            "Create intelligent rules while tagging to automate future similar transactions."
        )

        manual_tab, bulk_tab, edit_tab = st.tabs([
            "Manual Tagging",
            "Bulk Tagging",
            "Edit Transactions"
        ])

        with manual_tab:
            self._render_manual_tagging()

        with bulk_tab:
            self._render_bulk_tagging()

        with edit_tab:
            self._render_transaction_editing()

    def _render_manual_tagging(self) -> None:
        """Render the manual tagging interface."""
        st.markdown("### Manual Transaction Tagging")
        st.markdown(
            "Select transactions to tag individually and optionally create rules for automatic tagging of similar transactions."
        )

        # Service selection
        service = st.selectbox(
            "Select transaction type:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="manual_tagging_service_selector"
        )

        # Get untagged transactions
        untagged_transactions = self.rules_service.get_untagged_transactions(service)

        # Option to view tagged transactions for re-tagging
        show_tagged = st.checkbox("Show already tagged transactions for re-tagging", key="manual_show_tagged")

        if show_tagged:
            all_transactions = self.transactions_service.get_all_transactions(service)
            if not all_transactions.empty:
                st.info(f"Showing all {len(all_transactions)} transactions for re-tagging")
                self._render_transaction_filter(all_transactions, service, show_tagged=True)
            else:
                st.info("No transactions found.")
            return

        if untagged_transactions.empty:
            st.info("🎉 No untagged transactions found. All transactions have been categorized!")
            st.info("Use the checkbox above to view and edit already tagged transactions.")
            return

        # Filter interface for untagged transactions
        self._render_transaction_filter(untagged_transactions, service)

    def _render_bulk_tagging(self) -> None:
        """Render bulk tagging operations."""
        st.markdown("### Bulk Transaction Operations")
        st.markdown("Perform operations on multiple transactions at once.")

        # Service selection
        service = st.selectbox(
            "Select transaction type:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="bulk_tagging_service_selector"
        )

        # Get all transactions
        all_transactions = self.transactions_service.get_all_transactions(service)

        if all_transactions.empty:
            st.info("No transactions found.")
            return

        # Filter for bulk operations
        filter_col, bulk_col = st.columns([0.4, 0.6])

        with filter_col:
            st.markdown("**Filter Transactions**")

            # Create filter widgets for bulk operations
            widgets_map = {
                TransactionsTableFields.AMOUNT.value: 'number_range',
                TransactionsTableFields.DATE.value: 'date_range',
                TransactionsTableFields.PROVIDER.value: 'multiselect',
                TransactionsTableFields.DESCRIPTION.value: 'text_contains',
                TransactionsTableFields.CATEGORY.value: 'multiselect',
                TransactionsTableFields.TAG.value: 'multiselect',
            }

            if f"bulk_filter_widgets_{service}" not in st.session_state:
                df_filter = PandasFilterWidgets(all_transactions, widgets_map, keys_prefix=f"bulk_{service}")
                st.session_state[f"bulk_filter_widgets_{service}"] = df_filter
            else:
                df_filter = st.session_state[f"bulk_filter_widgets_{service}"]

            df_filter.display_widgets()
            filtered_transactions = df_filter.filter_df()

            st.info(f"Found {len(filtered_transactions)} matching transactions")

        with bulk_col:
            if filtered_transactions.empty:
                st.info("No transactions match the current filters.")
                return

            # Bulk tagging controls
            st.markdown("**Bulk Actions**")

            col_cat, col_tag = st.columns(2)
            with col_cat:
                categories = list(self.categories_and_tags.keys())
                bulk_category = st.selectbox(
                    "Category to apply:",
                    options=[None] + categories,
                    format_func=lambda x: "Select category..." if x is None else x,
                    key=f'bulk_category_{service}'
                )

            with col_tag:
                tags = self.categories_and_tags.get(bulk_category, []) if bulk_category else []
                bulk_tag = st.selectbox(
                    "Tag to apply:",
                    options=[None] + tags,
                    format_func=lambda x: "Select tag..." if x is None else x,
                    key=f'bulk_tag_{service}'
                )

            # Action selection
            st.markdown("**Select Action**")
            action_type = st.radio(
                "Action:",
                options=["apply_tags", "remove_tags"],
                format_func=lambda x: "Apply selected category/tag" if x == "apply_tags" else "Remove all tags",
                key=f"bulk_action_{service}"
            )

            # Preview and confirm
            if action_type == "apply_tags" and bulk_category and bulk_tag:
                st.success(f"Ready to apply **{bulk_category}/{bulk_tag}** to {len(filtered_transactions)} transactions")

                if st.button(f"💾 Save - Apply {bulk_category}/{bulk_tag}",
                           type="primary", key=f"bulk_save_apply_{service}"):
                    self._apply_bulk_tagging(filtered_transactions, service, bulk_category, bulk_tag)
                    st.success(f"✅ Applied {bulk_category}/{bulk_tag} to {len(filtered_transactions)} transactions!")
                    # Clear cache and rerun
                    if f"bulk_filter_widgets_{service}" in st.session_state:
                        del st.session_state[f"bulk_filter_widgets_{service}"]
                    st.rerun()

            elif action_type == "remove_tags":
                st.warning(f"Ready to remove all tags from {len(filtered_transactions)} transactions")

                if st.button(f"💾 Save - Remove All Tags",
                           type="secondary", key=f"bulk_save_remove_{service}"):
                    self._apply_bulk_tag_removal(filtered_transactions, service)
                    st.success(f"✅ Removed tags from {len(filtered_transactions)} transactions!")
                    # Clear cache and rerun
                    if f"bulk_filter_widgets_{service}" in st.session_state:
                        del st.session_state[f"bulk_filter_widgets_{service}"]
                    st.rerun()

            elif action_type == "apply_tags":
                st.info("Please select both category and tag to proceed.")

            # Preview table
            if not filtered_transactions.empty:
                st.markdown("**Preview Transactions**")
                columns_order = self.transactions_service.get_table_columns_for_display()
                st.dataframe(
                    filtered_transactions.head(10),
                    column_order=columns_order,
                    hide_index=True,
                    height=300
                )
                if len(filtered_transactions) > 10:
                    st.info(f"Showing first 10 of {len(filtered_transactions)} transactions")

    def _render_transaction_editing(self) -> None:
        """Render transaction data editing interface."""
        st.markdown("### Edit Transaction Data")
        st.markdown("Select a transaction to edit its details (description, amount, provider, etc.)")

        # Service selection
        service = st.selectbox(
            "Select transaction type:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="edit_service_selector"
        )

        # Get all transactions for editing
        all_transactions = self.transactions_service.get_all_transactions(service)

        if all_transactions.empty:
            st.info("No transactions found.")
            return

        # Filter interface using comprehensive widgets
        filter_col, data_col = st.columns([0.3, 0.7])

        with filter_col:
            st.markdown("**Filter Transactions**")

            # Create filter widgets for editing operations
            filter_key = f"edit_filter_widgets_{service}"
            if filter_key not in st.session_state:
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

                df_filter = PandasFilterWidgets(all_transactions, widgets_map, keys_prefix=f"edit_{service}")
                st.session_state[filter_key] = df_filter
            else:
                df_filter = st.session_state[filter_key]

            df_filter.display_widgets()
            filtered_transactions = df_filter.filter_df()

            st.info(f"Found {len(filtered_transactions)} transactions")

        with data_col:
            if filtered_transactions.empty:
                st.info("No transactions match the current filters.")
                return

            # Transaction selection
            columns_order = self.transactions_service.get_table_columns_for_display()

            selections = st.dataframe(
                filtered_transactions,
                key=f'{service}_edit_dataframe',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
                height=400
            )

            # Handle selected transaction for editing
            indices = selections['selection']['rows']
            if indices:
                idx = indices[0]
                selected_transaction = filtered_transactions.iloc[idx]
                self._render_transaction_editor(selected_transaction, service)

    def _render_transaction_editor(self, transaction: pd.Series, service: str) -> None:
        """Render the transaction editor interface."""
        st.markdown("---")
        st.markdown("#### Edit Transaction Details")

        id_col = TransactionsTableFields.ID.value
        transaction_id = transaction[id_col]

        with st.container(border=True):
            self._transaction_editor_fragment(transaction, service, transaction_id)

    @st.fragment
    def _transaction_editor_fragment(self, transaction: pd.Series, service: str, transaction_id: str) -> None:
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

            service_literal: Literal['credit_card', 'bank'] = service
            success = self.transactions_service.update_transaction_by_id(
                transaction_id, updates, service_literal
            )

            if success:
                st.success("✅ Transaction updated successfully!")
                st.rerun()
            else:
                st.error("❌ Failed to update transaction")

    def _apply_bulk_tagging(self, transactions: pd.DataFrame, service: str, category: str, tag: str) -> None:
        """Apply bulk tagging to multiple transactions."""
        service_literal: Literal['credit_card', 'bank'] = service
        id_col = TransactionsTableFields.ID.value

        for _, transaction in transactions.iterrows():
            self.transactions_service.update_tagging_by_id(
                transaction[id_col], category, tag, service_literal
            )

    def _apply_bulk_tag_removal(self, transactions: pd.DataFrame, service: str) -> None:
        """Remove tags from multiple transactions."""
        service_literal: Literal['credit_card', 'bank'] = service
        id_col = TransactionsTableFields.ID.value

        for _, transaction in transactions.iterrows():
            self.transactions_service.update_tagging_by_id(
                transaction[id_col], None, None, service_literal
            )

    def _render_transaction_filter(self, transactions: pd.DataFrame, service: str, show_tagged: bool = False) -> None:
        """Render transaction filtering and selection interface."""
        tag_status = "tagged" if show_tagged else "untagged"
        st.markdown(f"#### {tag_status.title()} {service.replace('_', ' ').title()} Transactions ({len(transactions)})")

        # Filter widgets
        filter_col, data_col = st.columns([0.3, 0.7])

        with filter_col:
            # Create filter widgets
            filter_key = f"manual_filter_widgets_{service}_{tag_status}"
            if filter_key not in st.session_state:
                widgets_map = {
                    TransactionsTableFields.AMOUNT.value: 'number_range',
                    TransactionsTableFields.DATE.value: 'date_range',
                    TransactionsTableFields.PROVIDER.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
                    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
                }

                df_filter = PandasFilterWidgets(transactions, widgets_map, keys_prefix=f"manual_{service}_{tag_status}")
                st.session_state[filter_key] = df_filter
            else:
                df_filter = st.session_state[filter_key]

            df_filter.display_widgets()
            filtered_transactions = df_filter.filter_df()

        with data_col:
            if filtered_transactions.empty:
                st.info("No transactions match the current filters.")
                return

            # Display transactions with selection
            columns_order = self.transactions_service.get_table_columns_for_display()

            selections = st.dataframe(
                filtered_transactions,
                key=f'{service}_manual_dataframe_{tag_status}',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
            )

            # Handle selected transaction
            indices = selections['selection']['rows']
            for idx in indices:
                row = filtered_transactions.iloc[idx]
                self.render_transaction_tagger(row, service)

    def render_transaction_tagger(self, transaction: pd.Series, service: str) -> None:
        """Render the interface for tagging a single transaction and creating rules."""
        st.markdown("---")
        st.markdown("#### Tag Selected Transaction")

        # Display transaction details
        desc_col = TransactionsTableFields.DESCRIPTION.value
        amount_col = TransactionsTableFields.AMOUNT.value
        provider_col = TransactionsTableFields.PROVIDER.value

        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Description:** {transaction[desc_col]}")
        with col2:
            st.write(f"**Amount:** {transaction[amount_col]}")
        with col3:
            st.write(f"**Provider:** {transaction[provider_col]}")

        # Check if transaction has splits
        id_col = TransactionsTableFields.ID.value
        service_literal: Literal['credit_card', 'bank'] = service
        has_splits = self.split_transactions_service.has_splits(transaction[id_col], service_literal)

        if has_splits:
            st.info("This transaction has been split. Edit splits to modify tagging.")
            if st.button("Edit Split Transaction", key=f"edit_split_{transaction[id_col]}"):
                self._render_split_transaction_ui(transaction, service)
            return

        # Manual tagging interface
        self._render_manual_tagging_interface(transaction, service)

        # Rule creation interface - delegate to rule component
        with st.expander("🤖 Create Rule for Similar Transactions", expanded=False):
            self.rule_component.render_rule_creation_interface(transaction, service)

    def _render_manual_tagging_interface(self, transaction: pd.Series, service: str) -> None:
        """Render manual tagging interface for a transaction."""
        # Get current category and tag
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        id_col = TransactionsTableFields.ID.value

        current_category = transaction.get(category_col)
        current_tag = transaction.get(tag_col)

        col_cat, col_tag, col_save, col_remove, col_split = st.columns([0.2, 0.2, 0.2, 0.2, 0.2])

        with col_cat:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                "Category",
                options=[None] + categories,
                index=categories.index(current_category) + 1 if current_category in categories else 0,
                format_func=lambda x: "No category" if x is None else x,
                key=f'manual_category_{transaction[id_col]}'
            )

        with col_tag:
            tags = self.categories_and_tags.get(category, []) if category else []
            tag = st.selectbox(
                "Tag",
                options=[None] + tags,
                index=tags.index(current_tag) + 1 if current_tag in tags and category else 0,
                format_func=lambda x: "No tag" if x is None else x,
                key=f'manual_tag_{transaction[id_col]}'
            )

        with col_save:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Save', key=f'save_manual_{transaction[id_col]}'):
                if category and tag:
                    service_literal: Literal['credit_card', 'bank'] = service
                    self.transactions_service.update_tagging_by_id(
                        transaction[id_col], category, tag, service_literal
                    )
                    # Clear filter cache
                    filter_keys = [
                        f"manual_filter_widgets_{service}_untagged",
                        f"manual_filter_widgets_{service}_tagged"
                    ]
                    for filter_key in filter_keys:
                        if filter_key in st.session_state:
                            del st.session_state[filter_key]
                    st.success("Transaction tagged successfully!")
                    st.rerun()
                else:
                    st.error("Please select both category and tag.")

        with col_remove:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Remove Tags', key=f'remove_tags_{transaction[id_col]}', type="secondary"):
                service_literal: Literal['credit_card', 'bank'] = service
                self.transactions_service.update_tagging_by_id(
                    transaction[id_col], None, None, service_literal
                )
                # Clear filter cache
                filter_keys = [
                    f"manual_filter_widgets_{service}_untagged",
                    f"manual_filter_widgets_{service}_tagged"
                ]
                for filter_key in filter_keys:
                    if filter_key in st.session_state:
                        del st.session_state[filter_key]
                st.success("Transaction tags removed!")
                st.rerun()

        with col_split:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Split Transaction', key=f'split_{transaction[id_col]}'):
                st.session_state[f'show_split_{transaction[id_col]}'] = True
                st.rerun()

        # Show split interface if requested
        if st.session_state.get(f'show_split_{transaction[id_col]}', False):
            self._render_split_transaction_ui(transaction, service)

    def _render_split_transaction_ui(self, transaction: pd.Series, service: str) -> None:
        """Render split transaction interface."""
        st.markdown("#### Split Transaction")
        st.info("Split transaction functionality would be implemented here.")
        # This would integrate with the split transactions service
