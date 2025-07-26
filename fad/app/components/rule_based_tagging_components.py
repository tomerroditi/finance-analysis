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
            "Select transactions to tag manually and optionally create rules for automatic tagging of similar transactions."
        )

        # Service selection
        service = st.selectbox(
            "Select transaction type:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="tagging_service_selector"
        )

        # Get untagged transactions
        untagged_transactions = self.rules_service.get_untagged_transactions(service)

        if untagged_transactions.empty:
            st.info("No untagged transactions found. All transactions have been categorized!")
            return

        # Filter interface
        self._render_transaction_filter(untagged_transactions, service)

    def _render_transaction_filter(self, transactions: pd.DataFrame, service: str) -> None:
        """Render transaction filtering and selection interface."""
        st.markdown(f"#### Untagged {service.replace('_', ' ').title()} Transactions ({len(transactions)})")

        # Filter widgets
        filter_col, data_col = st.columns([0.3, 0.7])

        with filter_col:
            # Create filter widgets
            if f"tagging_filter_widgets_{service}" not in st.session_state:
                widgets_map = {
                    TransactionsTableFields.AMOUNT.value: 'number_range',
                    TransactionsTableFields.DATE.value: 'date_range',
                    TransactionsTableFields.PROVIDER.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
                    TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
                    TransactionsTableFields.DESCRIPTION.value: 'multiselect',
                }

                df_filter = PandasFilterWidgets(transactions, widgets_map, keys_prefix=f"tagging_{service}")
                st.session_state[f"tagging_filter_widgets_{service}"] = df_filter
            else:
                df_filter = st.session_state[f"tagging_filter_widgets_{service}"]

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
                key=f'{service}_tagging_dataframe',
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
        service_literal: Literal['credit_card', 'bank'] = service  # Type assertion for proper typing
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

        col_cat, col_tag, col_save, col_split = st.columns([0.25, 0.25, 0.25, 0.25])

        with col_cat:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                "Category",
                options=categories,
                index=categories.index(current_category) if current_category in categories else None,
                key=f'manual_category_{transaction[id_col]}'
            )

        with col_tag:
            tags = self.categories_and_tags.get(category, []) if category else []
            tag = st.selectbox(
                "Tag",
                options=tags,
                index=tags.index(current_tag) if current_tag in tags else None,
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
                    filter_key = f"tagging_filter_widgets_{service}"
                    if filter_key in st.session_state:
                        del st.session_state[filter_key]
                    st.success("Transaction tagged successfully!")
                    st.rerun()
                else:
                    st.error("Please select both category and tag.")

        with col_split:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button('Split Transaction', key=f'split_{transaction[id_col]}'):
                st.session_state[f'show_split_{transaction[id_col]}'] = True
                st.rerun()

        # Show split interface if requested
        if st.session_state.get(f'show_split_{transaction[id_col]}', False):
            self._render_split_transaction_ui(transaction, service)

    def _render_rule_creation_interface(self, transaction: pd.Series, service: str) -> None:
        """Render interface for creating rules based on a transaction."""
        st.markdown("Create a rule to automatically tag similar transactions in the future.")

        # Get rule suggestions
        service_literal: Literal['credit_card', 'bank'] = service
        suggestions = self.rules_service.get_rule_suggestions(transaction, service_literal)

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
            if suggestions and st.button("🎯 Add Suggested Condition", key=f"add_suggested_{transaction[TransactionsTableFields.ID.value]}"):
                # Add the first suggestion
                suggestion = suggestions[0]
                st.session_state[conditions_key].append({
                    'field': suggestion['field'],
                    'operator': suggestion['operator'],
                    'value': suggestion['value']
                })
                st.rerun()

        # Show suggestions
        if suggestions:
            st.markdown("**Suggestions:**")
            for i, suggestion in enumerate(suggestions[:3]):  # Show top 3
                if st.button(
                    f"📋 {suggestion['description']}",
                    key=f"suggestion_{i}_{transaction[TransactionsTableFields.ID.value]}"
                ):
                    st.session_state[conditions_key].append({
                        'field': suggestion['field'],
                        'operator': suggestion['operator'],
                        'value': suggestion['value']
                    })
                    st.rerun()

        # Category and tag selection for rule
        if conditions:
            col_cat, col_tag, col_priority = st.columns([1, 1, 1])

            with col_cat:
                categories = list(self.categories_and_tags.keys())
                rule_category = st.selectbox(
                    "Rule Category",
                    options=categories,
                    key=f'rule_category_{transaction[TransactionsTableFields.ID.value]}'
                )

            with col_tag:
                rule_tags = self.categories_and_tags.get(rule_category, []) if rule_category else []
                rule_tag = st.selectbox(
                    "Rule Tag",
                    options=rule_tags,
                    key=f'rule_tag_{transaction[TransactionsTableFields.ID.value]}'
                )

            with col_priority:
                rule_priority = st.number_input(
                    "Priority",
                    min_value=1,
                    max_value=100,
                    value=10,
                    help="Higher numbers have higher priority",
                    key=f'rule_priority_{transaction[TransactionsTableFields.ID.value]}'
                )

            # Preview matching transactions
            if st.button("🔍 Preview Matches", key=f"preview_{transaction[TransactionsTableFields.ID.value]}"):
                account_number = transaction.get(TransactionsTableFields.ACCOUNT_NUMBER.value) if service == 'bank' else None
                matching_transactions = self.rules_service.test_rule_against_transactions(
                    conditions, service_literal, account_number, limit=10
                )

                if not matching_transactions.empty:
                    st.success(f"Found {len(matching_transactions)} matching transactions")
                    st.dataframe(matching_transactions[[
                        TransactionsTableFields.DESCRIPTION.value,
                        TransactionsTableFields.AMOUNT.value,
                        TransactionsTableFields.DATE.value
                    ]])
                else:
                    st.warning("No matching transactions found")

            # Create rule button
            col_create, col_apply = st.columns([1, 1])
            with col_create:
                if st.button("💾 Create Rule", key=f"create_rule_{transaction[TransactionsTableFields.ID.value]}"):
                    if rule_name and rule_category and rule_tag and conditions:
                        # Validate conditions
                        errors = self.rules_service.validate_conditions(conditions)
                        if errors:
                            st.error("Rule validation failed:")
                            for error in errors:
                                st.error(f"• {error}")
                        else:
                            # Create the rule
                            account_number = transaction.get(TransactionsTableFields.ACCOUNT_NUMBER.value) if service == 'bank' else None
                            rule_id = self.rules_service.create_rule(
                                name=rule_name,
                                conditions=conditions,
                                category=rule_category,
                                tag=rule_tag,
                                service=service_literal,
                                priority=rule_priority,
                                account_number=account_number
                            )
                            st.success(f"Rule created successfully! (ID: {rule_id})")

                            # Clear conditions
                            st.session_state[conditions_key] = []
                    else:
                        st.error("Please provide rule name, category, tag, and at least one condition.")

            with col_apply:
                if st.button("💾 Create & Apply Now", key=f"create_apply_{transaction[TransactionsTableFields.ID.value]}"):
                    if rule_name and rule_category and rule_tag and conditions:
                        errors = self.rules_service.validate_conditions(conditions)
                        if errors:
                            st.error("Rule validation failed:")
                            for error in errors:
                                st.error(f"• {error}")
                        else:
                            # Create rule and apply to transactions
                            account_number = transaction.get(TransactionsTableFields.ACCOUNT_NUMBER.value) if service == 'bank' else None
                            rule_id = self.rules_service.create_rule(
                                name=rule_name,
                                conditions=conditions,
                                category=rule_category,
                                tag=rule_tag,
                                service=service_literal,
                                priority=rule_priority,
                                account_number=account_number
                            )

                            # Apply rules
                            tagged_count = self.rules_service.apply_rules_to_transactions(service_literal)

                            st.success(f"Rule created and applied! Tagged {tagged_count} transactions.")

                            # Clear conditions and refresh
                            st.session_state[conditions_key] = []
                            if f"tagging_filter_widgets_{service}" in st.session_state:
                                del st.session_state[f"tagging_filter_widgets_{service}"]
                            st.rerun()
                    else:
                        st.error("Please provide rule name, category, tag, and at least one condition.")

    def _render_condition_editor(self, index: int, condition: Dict[str, Any], conditions_key: str) -> None:
        """Render editor for a single rule condition."""
        col1, col2, col3, col4 = st.columns([0.2, 0.2, 0.4, 0.2])

        with col1:
            field_options = [field.value for field in RuleFields]
            field_labels = {
                RuleFields.DESCRIPTION.value: "Description",
                RuleFields.AMOUNT.value: "Amount",
                RuleFields.PROVIDER.value: "Provider",
                RuleFields.ACCOUNT_NAME.value: "Account Name",
                RuleFields.ACCOUNT_NUMBER.value: "Account Number",
            }

            field = st.selectbox(
                "Field",
                options=field_options,
                format_func=lambda x: field_labels.get(x, x),
                index=field_options.index(condition['field']) if condition['field'] in field_options else 0,
                key=f"condition_field_{index}_{conditions_key}"
            )
            condition['field'] = field

        with col2:
            # Operator options depend on field type
            if field == RuleFields.AMOUNT.value:
                operator_options = [
                    RuleOperators.EQUALS.value,
                    RuleOperators.GREATER_THAN.value,
                    RuleOperators.LESS_THAN.value,
                    RuleOperators.GREATER_THAN_EQUAL.value,
                    RuleOperators.LESS_THAN_EQUAL.value,
                    RuleOperators.BETWEEN.value,
                ]
            else:
                operator_options = [
                    RuleOperators.CONTAINS.value,
                    RuleOperators.EQUALS.value,
                    RuleOperators.STARTS_WITH.value,
                    RuleOperators.ENDS_WITH.value,
                ]

            operator_labels = {
                RuleOperators.CONTAINS.value: "Contains",
                RuleOperators.EQUALS.value: "Equals",
                RuleOperators.STARTS_WITH.value: "Starts with",
                RuleOperators.ENDS_WITH.value: "Ends with",
                RuleOperators.GREATER_THAN.value: ">",
                RuleOperators.LESS_THAN.value: "<",
                RuleOperators.GREATER_THAN_EQUAL.value: "≥",
                RuleOperators.LESS_THAN_EQUAL.value: "≤",
                RuleOperators.BETWEEN.value: "Between",
            }

            operator = st.selectbox(
                "Operator",
                options=operator_options,
                format_func=lambda x: operator_labels.get(x, x),
                index=operator_options.index(condition['operator']) if condition['operator'] in operator_options else 0,
                key=f"condition_operator_{index}_{conditions_key}"
            )
            condition['operator'] = operator

        with col3:
            # Value input depends on operator
            if operator == RuleOperators.BETWEEN.value:
                val_col1, val_col2 = st.columns(2)
                with val_col1:
                    min_val = st.number_input(
                        "Min",
                        value=float(condition['value'][0]) if isinstance(condition.get('value'), list) and len(condition['value']) >= 1 else 0.0,
                        key=f"condition_value_min_{index}_{conditions_key}"
                    )
                with val_col2:
                    max_val = st.number_input(
                        "Max",
                        value=float(condition['value'][1]) if isinstance(condition.get('value'), list) and len(condition['value']) >= 2 else 100.0,
                        key=f"condition_value_max_{index}_{conditions_key}"
                    )
                condition['value'] = [min_val, max_val]
            elif field == RuleFields.AMOUNT.value and operator != RuleOperators.BETWEEN.value:
                value = st.number_input(
                    "Value",
                    value=float(condition.get('value', 0)) if condition.get('value') else 0.0,
                    key=f"condition_value_{index}_{conditions_key}"
                )
                condition['value'] = value
            else:
                value = st.text_input(
                    "Value",
                    value=str(condition.get('value', '')),
                    key=f"condition_value_{index}_{conditions_key}"
                )
                condition['value'] = value

        with col4:
            if st.button("🗑️", key=f"remove_condition_{index}_{conditions_key}", help="Remove condition"):
                st.session_state[conditions_key].pop(index)
                st.rerun()

    def _render_split_transaction_ui(self, transaction: pd.Series, service: str) -> None:
        """Render split transaction interface."""
        st.markdown("#### Split Transaction")
        st.info("Split transaction functionality will be implemented here. For now, you can manually split transactions using the existing split transaction service.")

        # For now, show basic info and provide a way to close the split UI
        if st.button("Close Split Interface", key=f"close_split_{transaction[TransactionsTableFields.ID.value]}"):
            st.session_state[f'show_split_{transaction[TransactionsTableFields.ID.value]}'] = False
            st.rerun()

    def _render_rule_management(self) -> None:
        """Render the rule management interface."""
        st.markdown("### Rule Management")

        # Service filter
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            service_filter = st.selectbox(
                "Filter by service:",
                options=[None, "credit_card", "bank"],
                format_func=lambda x: "All Services" if x is None else ("Credit Card" if x == "credit_card" else "Bank"),
                key="rules_service_filter"
            )

        with col2:
            if st.button("🔄 Apply All Rules", type="primary"):
                results = self.rules_service.apply_rules_to_all_services()
                total_tagged = sum(results.values())
                st.success(f"Applied rules! Tagged {total_tagged} transactions.")
                for service, count in results.items():
                    st.info(f"{service.replace('_', ' ').title()}: {count} transactions")

        # Get rules
        rules_df = self.rules_service.get_all_rules(service=service_filter)

        if rules_df.empty:
            st.info("No rules found. Create your first rule in the Transaction Tagging tab!")
            return

        # Display rules table
        st.markdown("#### Existing Rules")

        # Format rules for display
        display_rules = rules_df.copy()
        display_rules['conditions_summary'] = display_rules['conditions'].apply(self._format_conditions_summary)
        display_rules['service_display'] = display_rules['service'].apply(lambda x: x.replace('_', ' ').title())

        display_columns = ['id', 'name', 'priority', 'conditions_summary', 'category', 'tag', 'service_display', 'is_active']
        column_labels = {
            'id': 'ID',
            'name': 'Name',
            'priority': 'Priority',
            'conditions_summary': 'Conditions',
            'category': 'Category',
            'tag': 'Tag',
            'service_display': 'Service',
            'is_active': 'Active'
        }

        selections = st.dataframe(
            display_rules[display_columns],
            column_config={col: st.column_config.Column(label) for col, label in column_labels.items()},
            on_select='rerun',
            selection_mode='single-row',
            hide_index=True,
            use_container_width=True
        )

        # Handle rule selection
        selected_indices = selections['selection']['rows']
        if selected_indices:
            selected_rule_id = display_rules.iloc[selected_indices[0]]['id']
            self._render_rule_editor(selected_rule_id)

    def _format_conditions_summary(self, conditions_json: str) -> str:
        """Format rule conditions for display in the table."""
        try:
            conditions = json.loads(conditions_json)
            if not conditions:
                return "No conditions"

            summaries = []
            for condition in conditions[:2]:  # Show first 2 conditions
                field = condition.get('field', '')
                operator = condition.get('operator', '')
                value = condition.get('value', '')

                if operator == 'between' and isinstance(value, list):
                    value_str = f"{value[0]}-{value[1]}"
                else:
                    value_str = str(value)[:20]

                summaries.append(f"{field} {operator} {value_str}")

            result = "; ".join(summaries)
            if len(conditions) > 2:
                result += f" (+{len(conditions) - 2} more)"

            return result
        except (json.JSONDecodeError, KeyError):
            return "Invalid conditions"

    def _render_rule_editor(self, rule_id: int) -> None:
        """Render interface for editing a specific rule."""
        st.markdown("---")
        st.markdown("#### Edit Rule")

        rule = self.rules_service.get_rule_by_id(rule_id)
        if not rule:
            st.error("Rule not found!")
            return

        col1, col2 = st.columns([2, 1])

        with col1:
            # Rule details
            updated_name = st.text_input("Rule Name", value=rule['name'], key=f"edit_name_{rule_id}")
            updated_priority = st.number_input(
                "Priority",
                min_value=1,
                max_value=100,
                value=rule['priority'],
                key=f"edit_priority_{rule_id}"
            )
            updated_is_active = st.checkbox("Active", value=bool(rule['is_active']), key=f"edit_active_{rule_id}")

            # Conditions editor
            st.markdown("**Conditions:**")
            conditions = rule['conditions'].copy()

            for i, condition in enumerate(conditions):
                self._render_condition_editor(i, condition, f"edit_rule_{rule_id}")

            if st.button("➕ Add Condition", key=f"add_condition_edit_{rule_id}"):
                conditions.append({
                    'field': RuleFields.DESCRIPTION.value,
                    'operator': RuleOperators.CONTAINS.value,
                    'value': ''
                })
                rule['conditions'] = conditions

        with col2:
            # Actions
            st.markdown("**Actions:**")

            if st.button("💾 Save Changes", key=f"save_rule_{rule_id}", type="primary"):
                success = self.rules_service.update_rule(
                    rule_id,
                    name=updated_name,
                    conditions=conditions,
                    priority=updated_priority,
                    is_active=updated_is_active
                )

                if success:
                    st.success("Rule updated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to update rule.")

            if st.button("🗑️ Delete Rule", key=f"delete_rule_{rule_id}"):
                if st.session_state.get(f"confirm_delete_{rule_id}", False):
                    success = self.rules_service.delete_rule(rule_id)
                    if success:
                        st.success("Rule deleted successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to delete rule.")
                else:
                    st.session_state[f"confirm_delete_{rule_id}"] = True
                    st.warning("Click again to confirm deletion.")

            if st.button("🔍 Test Rule", key=f"test_rule_{rule_id}"):
                service = rule['service']
                account_number = rule.get('account_number')
                matching_transactions = self.rules_service.test_rule_against_transactions(
                    conditions, service, account_number, limit=10
                )

                if not matching_transactions.empty:
                    st.success(f"Found {len(matching_transactions)} matching transactions")
                    st.dataframe(matching_transactions[[
                        TransactionsTableFields.DESCRIPTION.value,
                        TransactionsTableFields.AMOUNT.value,
                        TransactionsTableFields.DATE.value
                    ]])
                else:
                    st.info("No matching transactions found")

    def _render_rule_testing(self) -> None:
        """Render the rule testing interface."""
        st.markdown("### Rule Testing")
        st.markdown("Test rule conditions against existing transactions to see what would match.")

        # Service selection
        service = st.selectbox(
            "Select service:",
            options=["credit_card", "bank"],
            format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
            key="test_service_selector"
        )

        # Conditions builder for testing
        st.markdown("**Test Conditions:**")

        # Initialize test conditions
        test_conditions_key = "test_rule_conditions"
        if test_conditions_key not in st.session_state:
            st.session_state[test_conditions_key] = []

        conditions = st.session_state[test_conditions_key]

        # Display conditions
        for i, condition in enumerate(conditions):
            self._render_condition_editor(i, condition, test_conditions_key)

        # Add condition button
        if st.button("➕ Add Condition", key="add_test_condition"):
            st.session_state[test_conditions_key].append({
                'field': RuleFields.DESCRIPTION.value,
                'operator': RuleOperators.CONTAINS.value,
                'value': ''
            })
            st.rerun()

        # Test button
        if conditions and st.button("🔍 Test Conditions", type="primary"):
            service_literal: Literal['credit_card', 'bank'] = service
            matching_transactions = self.rules_service.test_rule_against_transactions(
                conditions, service_literal, limit=50
            )

            if not matching_transactions.empty:
                st.success(f"Found {len(matching_transactions)} matching transactions")

                # Display results
                display_columns = [
                    TransactionsTableFields.DESCRIPTION.value,
                    TransactionsTableFields.AMOUNT.value,
                    TransactionsTableFields.DATE.value,
                    TransactionsTableFields.PROVIDER.value,
                    TransactionsTableFields.CATEGORY.value,
                    TransactionsTableFields.TAG.value
                ]

                st.dataframe(
                    matching_transactions[display_columns],
                    use_container_width=True
                )
            else:
                st.info("No matching transactions found with the current conditions.")

        if not conditions:
            st.info("Add conditions above to test them against your transactions.")
