from typing import Dict, Any, Literal
import json

import pandas as pd
import streamlit as st

from fad.app.naming_conventions import (
    RuleOperators,
    RuleFields,
    TransactionsTableFields
)
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.app.services.split_transactions_service import SplitTransactionsService
from fad.app.services.tagging_service import CategoriesTagsService
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


class RuleBasedTaggingComponent:
    """
    Unified component for rule-based transaction tagging.

    This component provides:
    1. Rule management (create, edit, delete, prioritize)
    2. Transaction tagging with automatic rule creation
    3. Rule testing and preview
    """

    def __init__(self):
        self.rules_service = TaggingRulesService()
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService()
        self.split_transactions_service = SplitTransactionsService()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def render(self) -> None:
        """
        Render the rule-based tagging component UI.

        Creates tabs for different aspects of rule-based tagging:
        - Transaction Tagging: Manual tagging with rule creation
        - Rule Management: View, edit, delete, and prioritize rules
        - Rule Testing: Test rules against transactions
        """
        st.subheader("Transaction Tagging & Rule Management")
        st.markdown(
            "This system allows you to tag transactions manually and create intelligent rules that automatically tag similar transactions. "
            "Rules can match on description, amount, provider, and other transaction fields using various operators like 'contains', 'greater than', etc."
        )

        tagging_tab, rules_tab, testing_tab = st.tabs([
            "Transaction Tagging",
            "Rule Management",
            "Rule Testing"
        ])

        with tagging_tab:
            self._render_transaction_tagging()

        with rules_tab:
            self._render_rule_management()

        with testing_tab:
            self._render_rule_testing()

    def _render_transaction_tagging(self) -> None:
        """Render the transaction tagging interface with rule creation."""
        st.markdown("### Tag Transactions")
        st.markdown(
            "Select transactions to tag manually, edit transaction data, and optionally create rules for automatic tagging of similar transactions."
        )

        # Service selection
        service = st.selectbox(
            "Select transaction type:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="tagging_service_selector"
        )

        # Mode selection for enhanced functionality
        mode = st.radio(
            "Select mode:",
            options=["manual_tagging", "bulk_tagging", "edit_transactions"],
            format_func=lambda x: {
                "manual_tagging": "🏷️ Manual Tagging",
                "bulk_tagging": "📋 Bulk Tagging",
                "edit_transactions": "✏️ Edit Transaction Data"
            }[x],
            horizontal=True,
            key="tagging_mode"
        )

        if mode == "manual_tagging":
            self._render_manual_tagging_mode(service)
        elif mode == "bulk_tagging":
            self._render_bulk_tagging_mode(service)
        elif mode == "edit_transactions":
            self._render_transaction_editing_mode(service)

    def _render_manual_tagging_mode(self, service: str) -> None:
        """Render manual tagging mode for individual transactions."""
        # Get untagged transactions
        untagged_transactions = self.rules_service.get_untagged_transactions(service)

        # Always show option to view tagged transactions for re-tagging
        show_tagged = st.checkbox("Show already tagged transactions for re-tagging", key="show_tagged")

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

    def _render_bulk_tagging_mode(self, service: str) -> None:
        """Render bulk tagging mode for multiple transactions."""
        st.markdown("#### Bulk Tag Multiple Transactions")

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

    def _render_transaction_editing_mode(self, service: str) -> None:
        """Render transaction data editing mode."""
        st.markdown("#### Edit Transaction Data")
        st.markdown("Select a transaction to edit its details (description, amount, provider, etc.)")

        # Get all transactions for editing
        all_transactions = self.transactions_service.get_all_transactions(service)

        if all_transactions.empty:
            st.info("No transactions found.")
            return

        # Search and filter interface
        search_col, filter_col = st.columns([0.5, 0.5])

        with search_col:
            search_term = st.text_input(
                "Search transactions (description, provider):",
                key=f"edit_search_{service}"
            )

        with filter_col:
            date_range = st.date_input(
                "Date range:",
                value=None,
                key=f"edit_date_range_{service}"
            )

        # Filter transactions based on search and date
        filtered_transactions = all_transactions.copy()

        if search_term:
            desc_col = TransactionsTableFields.DESCRIPTION.value
            provider_col = TransactionsTableFields.PROVIDER.value
            mask = (
                filtered_transactions[desc_col].str.contains(search_term, case=False, na=False) |
                filtered_transactions[provider_col].str.contains(search_term, case=False, na=False)
            )
            filtered_transactions = filtered_transactions[mask]

        if date_range and len(date_range) == 2:
            date_col = TransactionsTableFields.DATE.value
            filtered_transactions = filtered_transactions[
                (pd.to_datetime(filtered_transactions[date_col]).dt.date >= date_range[0]) &
                (pd.to_datetime(filtered_transactions[date_col]).dt.date <= date_range[1])
            ]

        # Display transactions for editing
        if filtered_transactions.empty:
            st.info("No transactions match the search criteria.")
            return

        st.info(f"Found {len(filtered_transactions)} transactions")

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

        # Create editing form
        with st.form(f"edit_transaction_{transaction_id}"):
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
            submitted = st.form_submit_button("💾 Save Changes", type="primary")

            if submitted:
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
            filter_key = f"tagging_filter_widgets_{service}_{tag_status}"
            if filter_key not in st.session_state:
                widgets_map = {
                    TransactionsTableFields.AMOUNT.value: 'number_range',
                    TransactionsTableFields.DATE.value: 'date_range',
                    TransactionsTableFields.PROVIDER.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
                    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
                }

                df_filter = PandasFilterWidgets(transactions, widgets_map, keys_prefix=f"tagging_{service}_{tag_status}")
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
                key=f'{service}_tagging_dataframe_{tag_status}',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
            )

            # Handle selected transaction
            indices = selections['selection']['rows']
            for idx in indices:
                row = filtered_transactions.iloc[idx]
                self._render_transaction_tagger(row, service)

    def _render_transaction_tagger(self, transaction: pd.Series, service: str) -> None:
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

        # Rule creation interface
        with st.expander("🤖 Create Rule for Similar Transactions", expanded=False):
            self._render_rule_creation_interface(transaction, service)

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
                        f"tagging_filter_widgets_{service}_untagged",
                        f"tagging_filter_widgets_{service}_tagged"
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
                    f"tagging_filter_widgets_{service}_untagged",
                    f"tagging_filter_widgets_{service}_tagged"
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
        # For now, just provide a placeholder

    def _render_rule_creation_interface(self, transaction: pd.Series, service: str) -> None:
        """Render interface for creating rules based on a transaction."""
        st.markdown("Create a rule to automatically tag similar transactions in the future.")

        # Rule name
        desc_col = TransactionsTableFields.DESCRIPTION.value
        default_name = f"Rule for {transaction[desc_col][:30]}..."
        rule_name = st.text_input(
            "Rule Name",
            value=default_name,
            key=f"rule_name_{transaction[TransactionsTableFields.ID.value]}"
        )

        # Rule conditions builder
        st.markdown("**Conditions (all must match):**")

        # Initialize conditions in session state
        conditions_key = f"rule_conditions_{transaction[TransactionsTableFields.ID.value]}"
        if conditions_key not in st.session_state:
            st.session_state[conditions_key] = []

        # Display existing conditions
        conditions = st.session_state[conditions_key]
        for i, condition in enumerate(conditions):
            self._render_condition_editor(i, condition, conditions_key)

        # Add condition buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("➕ Add Empty Condition", key=f"add_empty_{transaction[TransactionsTableFields.ID.value]}"):
                st.session_state[conditions_key].append({
                    'field': RuleFields.DESCRIPTION.value,
                    'operator': RuleOperators.CONTAINS.value,
                    'value': ''
                })
                st.rerun()

        with col2:
            if st.button("🎯 Add Suggested Condition", key=f"add_suggested_{transaction[TransactionsTableFields.ID.value]}"):
                # Add a suggested condition based on transaction description
                st.session_state[conditions_key].append({
                    'field': RuleFields.DESCRIPTION.value,
                    'operator': RuleOperators.CONTAINS.value,
                    'value': transaction[desc_col][:20]  # First 20 characters
                })
                st.rerun()

        # Category and tag selection for rule
        col_cat, col_tag = st.columns(2)
        with col_cat:
            categories = list(self.categories_and_tags.keys())
            rule_category = st.selectbox(
                "Category for rule:",
                options=categories,
                key=f'rule_category_{transaction[TransactionsTableFields.ID.value]}'
            )

        with col_tag:
            tags = self.categories_and_tags.get(rule_category, []) if rule_category else []
            rule_tag = st.selectbox(
                "Tag for rule:",
                options=tags,
                key=f'rule_tag_{transaction[TransactionsTableFields.ID.value]}'
            )

        # Create rule button
        if st.button("🚀 Create Rule", key=f"create_rule_{transaction[TransactionsTableFields.ID.value]}"):
            if rule_name and conditions and rule_category and rule_tag:
                service_literal: Literal['credit_card', 'bank'] = service
                try:
                    rule_id = self.rules_service.add_rule(
                        name=rule_name,
                        conditions=conditions,
                        category=rule_category,
                        tag=rule_tag,
                        service=service_literal,
                        account_number=transaction.get(TransactionsTableFields.ACCOUNT_NUMBER.value) if service == 'bank' else None
                    )
                    st.success(f"✅ Rule created successfully! (ID: {rule_id})")
                    # Clear the conditions
                    st.session_state[conditions_key] = []
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to create rule: {str(e)}")
            else:
                st.error("Please provide rule name, at least one condition, category, and tag.")

    def _render_condition_editor(self, index: int, condition: dict, conditions_key: str) -> None:
        """Render a single condition editor."""
        col1, col2, col3, col4 = st.columns([0.25, 0.25, 0.4, 0.1])

        with col1:
            field = st.selectbox(
                "Field",
                options=[e.value for e in RuleFields],
                index=[e.value for e in RuleFields].index(condition['field']),
                key=f"field_{conditions_key}_{index}"
            )

        with col2:
            operator = st.selectbox(
                "Operator",
                options=[e.value for e in RuleOperators],
                index=[e.value for e in RuleOperators].index(condition['operator']),
                key=f"operator_{conditions_key}_{index}"
            )

        with col3:
            value = st.text_input(
                "Value",
                value=str(condition['value']),
                key=f"value_{conditions_key}_{index}"
            )

        with col4:
            if st.button("🗑️", key=f"delete_{conditions_key}_{index}"):
                st.session_state[conditions_key].pop(index)
                st.rerun()

        # Update the condition in session state
        st.session_state[conditions_key][index] = {
            'field': field,
            'operator': operator,
            'value': value
        }

    def _render_rule_management(self) -> None:
        """Render the rule management interface."""
        st.markdown("### Rule Management")
        st.markdown("Manage your tagging rules: view, edit, delete, and prioritize them.")

        # Service filter
        service_filter = st.selectbox(
            "Filter by service:",
            options=[None, "credit_card", "bank"],
            format_func=lambda x: "All Services" if x is None else ("Credit Card" if x == "credit_card" else "Bank"),
            key="rule_mgmt_service_filter"
        )

        # Get rules
        rules_df = self.rules_service.get_all_rules(service=service_filter, active_only=False)

        if rules_df.empty:
            st.info("No rules found. Create some rules in the Transaction Tagging tab!")
            return

        # Rules table
        col1, col2 = st.columns([0.6, 0.4])

        with col1:
            st.markdown("#### All Rules")

            # Display rules table
            display_columns = ['id', 'name', 'service', 'category', 'tag', 'priority', 'is_active']
            selections = st.dataframe(
                rules_df[display_columns],
                key="rules_management_table",
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                height=400
            )

        with col2:
            # Rule editor
            selected_rows = selections['selection']['rows']
            if selected_rows:
                selected_rule_id = rules_df.iloc[selected_rows[0]]['id']
                self._render_rule_editor(selected_rule_id)
            else:
                st.info("Select a rule from the table to edit it.")

    def _render_rule_editor(self, rule_id: int) -> None:
        """Render the rule editor interface."""
        st.markdown("#### Edit Rule")

        try:
            rule = self.rules_service.get_rule_by_id(rule_id)
            if rule is None:
                st.error("Rule not found!")
                return

            # Rule details form
            with st.form(f"edit_rule_{rule_id}"):
                new_name = st.text_input("Rule Name:", value=rule['name'])

                col1, col2 = st.columns(2)
                with col1:
                    categories = list(self.categories_and_tags.keys())
                    new_category = st.selectbox(
                        "Category:",
                        options=categories,
                        index=categories.index(rule['category']) if rule['category'] in categories else 0
                    )

                with col2:
                    tags = self.categories_and_tags.get(new_category, [])
                    new_tag = st.selectbox(
                        "Tag:",
                        options=tags,
                        index=tags.index(rule['tag']) if rule['tag'] in tags else 0
                    )

                new_priority = st.number_input("Priority:", value=int(rule['priority']), min_value=1, max_value=10)
                new_is_active = st.checkbox("Active", value=bool(rule['is_active']))

                # Conditions (read-only for now)
                st.markdown("**Conditions:**")
                for i, condition in enumerate(rule['conditions']):
                    st.text(f"{i+1}. {condition['field']} {condition['operator']} '{condition['value']}'")

                # Action buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.form_submit_button("💾 Save Changes"):
                        success = self.rules_service.update_rule(
                            rule_id=rule_id,
                            name=new_name,
                            category=new_category,
                            tag=new_tag,
                            priority=new_priority,
                            is_active=new_is_active
                        )
                        if success:
                            st.success("✅ Rule updated successfully!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to update rule")

                with col2:
                    if st.form_submit_button("🗑️ Delete Rule"):
                        success = self.rules_service.delete_rule(rule_id)
                        if success:
                            st.success("✅ Rule deleted successfully!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to delete rule")

                with col3:
                    if st.form_submit_button("🧪 Test Rule"):
                        # Test the rule against transactions
                        test_results = self.rules_service.test_rule(rule_id)
                        st.info(f"Rule would match {len(test_results)} transactions")

        except Exception as e:
            st.error(f"Error loading rule: {str(e)}")

    def _render_rule_testing(self) -> None:
        """Render the rule testing interface."""
        st.markdown("### Rule Testing")
        st.markdown("Test your rules against transactions to see how they would perform.")

        # Service selection
        service = st.selectbox(
            "Select service to test:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="test_service_selector"
        )

        # Get active rules for the service
        rules_df = self.rules_service.get_all_rules(service=service, active_only=True)

        if rules_df.empty:
            st.info(f"No active rules found for {service.replace('_', ' ').title()} service.")
            return

        # Rule selection
        rule_options = [(row['id'], f"{row['name']} ({row['category']}/{row['tag']})")
                       for _, row in rules_df.iterrows()]

        selected_rule_id = st.selectbox(
            "Select rule to test:",
            options=[r[0] for r in rule_options],
            format_func=lambda x: next(r[1] for r in rule_options if r[0] == x),
            key="test_rule_selector"
        )

        if st.button("🧪 Test Rule", key="test_rule_btn"):
            # Test the selected rule
            matching_transactions = self.rules_service.test_rule(selected_rule_id)

            if matching_transactions.empty:
                st.info("No transactions match this rule.")
            else:
                st.success(f"Found {len(matching_transactions)} matching transactions:")

                # Display matching transactions
                columns_order = self.transactions_service.get_table_columns_for_display()
                st.dataframe(
                    matching_transactions,
                    column_order=columns_order,
                    hide_index=True,
                    height=400
                )

        # Bulk rule application
        st.markdown("---")
        st.markdown("#### Apply All Rules")
        st.markdown("Apply all active rules to untagged transactions.")

        if st.button(f"🚀 Apply All {service.replace('_', ' ').title()} Rules", key="apply_all_rules"):
            tagged_count = self.rules_service.apply_all_rules(service)
            if tagged_count > 0:
                st.success(f"✅ Tagged {tagged_count} transactions!")
            else:
                st.info("No transactions were tagged. All may already be categorized or no rules matched.")
            st.rerun()
