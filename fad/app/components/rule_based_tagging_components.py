from typing import Literal, List
import pandas as pd
import streamlit as st

from fad.app.naming_conventions import (
    RuleOperators,
    RuleFields,
    TransactionsTableFields
)
from fad.app.services.tagging_rules_service import TaggingRulesService
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.services.transactions_service import TransactionsService


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
    Component for rule-based transaction tagging management.

    This component provides:
    1. Rule management (create, edit, delete, prioritize)
    2. Rule testing and preview
    3. Rule application to transactions
    """

    def __init__(self):
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
        st.subheader("Rule-Based Tagging Management")
        st.markdown(
            "Create and manage intelligent rules that automatically tag transactions based on description, amount, provider, and other fields. "
            "Rules use operators like 'contains', 'greater than', etc., to match transactions."
        )

        rules_tab, testing_tab, apply_tab = st.tabs([
            "Rule Management",
            "Rule Testing",
            "Apply Rules"
        ])

        with rules_tab:
            self._render_rule_management()

        with testing_tab:
            self._render_rule_testing()

        with apply_tab:
            self._render_rule_application()

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
                with st.container(border=True, key=f"rule_editor_{selected_rule_id}"):
                    self._render_rule_editor(selected_rule_id)
            else:
                st.info("Please select a rule from the table to edit it.")

    def _render_rule_editor(self, rule_id: int) -> None:
        """Render the rule editor interface."""
        st.markdown("#### Edit Rule")

        try:
            rule = self.rules_service.get_rule_by_id(rule_id)
            if rule is None:
                st.error("Rule not found!")
                return

            # Initialize conditions in session state for editing
            conditions_key = f"edit_rule_conditions_{rule_id}"
            if conditions_key not in st.session_state:
                st.session_state[conditions_key] = rule['conditions'].copy()

            self._rule_editor_fragment(rule, rule_id, conditions_key)

        except Exception as e:
            st.error(f"Error loading rule: {str(e)}")

    @st.fragment
    def _rule_editor_fragment(self, rule: dict, rule_id: int, conditions_key: str) -> None:
        """Fragment for rule editing form."""
        new_name = st.text_input("Rule Name:", value=rule['name'], key=f"edit_name_{rule_id}")

        col1, col2 = st.columns(2)
        with col1:
            categories = list(self.categories_and_tags.keys())
            new_category = st.selectbox(
                "Category:",
                options=categories,
                index=categories.index(rule['category']) if rule['category'] in categories else 0,
                key=f"edit_category_{rule_id}"
            )

        with col2:
            tags = self.categories_and_tags.get(new_category, [])
            new_tag = st.selectbox(
                "Tag:",
                options=tags,
                index=tags.index(rule['tag']) if rule['tag'] in tags else 0,
                key=f"edit_tag_{rule_id}"
            )

        new_priority = st.number_input("Priority:", value=int(rule['priority']), min_value=1, max_value=10, key=f"priority_{rule_id}")
        new_is_active = st.checkbox("Active", value=bool(rule['is_active']), key=f"active_{rule_id}")

        # Editable conditions section
        st.markdown("**Conditions (all must match):**")

        # Display existing conditions with edit capability
        conditions = st.session_state[conditions_key]
        for i, condition in enumerate(conditions):
            self._render_condition_editor_fragment(i, condition, conditions_key, rule_id)

        # Buttons to add/remove conditions
        col_add, col_remove = st.columns(2)
        with col_add:
            if st.button("➕ Add Condition", key=f"add_condition_{rule_id}"):
                st.session_state[conditions_key].append({
                    'field': RuleFields.DESCRIPTION.value,
                    'operator': RuleOperators.CONTAINS.value,
                    'value': ''
                })
                st.rerun()

        with col_remove:
            if len(conditions) > 1:  # Keep at least one condition
                if st.button("➖ Remove Last Condition", key=f"remove_condition_{rule_id}"):
                    st.session_state[conditions_key].pop()
                    st.rerun()

        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💾 Save Changes", key=f"save_rule_{rule_id}", type="primary"):
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
                    st.rerun()
                else:
                    st.error("❌ Failed to update rule")

        with col2:
            if st.button("🗑️ Delete Rule", key=f"delete_rule_{rule_id}", type="secondary"):
                success = self.rules_service.delete_rule(rule_id)
                if success:
                    st.success("✅ Rule deleted successfully!")
                    # Clear the session state for conditions
                    if conditions_key in st.session_state:
                        del st.session_state[conditions_key]
                    st.rerun()
                else:
                    st.error("❌ Failed to delete rule")

        with col3:
            if st.button("🧪 Test Rule", key=f"test_rule_{rule_id}"):
                # Test with current conditions from session state
                test_results = self.rules_service.test_rule_against_transactions(
                    conditions=st.session_state[conditions_key],
                    service=rule['service'],
                    account_number=rule.get('account_number')
                )
                st.info(f"Rule would match {len(test_results)} transactions")

    def _render_condition_editor_fragment(self, index: int, condition: dict, conditions_key: str, rule_id: int) -> None:
        """Render a condition editor for use within fragments."""
        col1, col2, col3 = st.columns([0.3, 0.3, 0.4])

        with col1:
            field = st.selectbox(
                f"Field {index + 1}",
                options=[e.value for e in RuleFields],
                index=[e.value for e in RuleFields].index(condition['field']) if condition['field'] in [e.value for e in RuleFields] else 0,
                key=f"edit_field_{rule_id}_{index}"
            )

        with col2:
            # Get available operators based on field type
            available_operators = self._get_operators_for_field(field)

            # Ensure current operator is valid for the field, otherwise use first available
            current_operator = condition['operator']
            if current_operator not in available_operators:
                current_operator = available_operators[0]

            operator = st.selectbox(
                f"Operator {index + 1}",
                options=available_operators,
                index=available_operators.index(current_operator) if current_operator in available_operators else 0,
                key=f"edit_operator_{rule_id}_{index}"
            )

        with col3:
            value = st.text_input(
                f"Value {index + 1}",
                value=str(condition['value']),
                key=f"edit_value_{rule_id}_{index}"
            )

        # Update the condition in session state
        st.session_state[conditions_key][index] = {
            'field': field,
            'operator': operator,
            'value': value
        }

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

    def _render_rule_application(self) -> None:
        """Render rule application interface."""
        st.markdown("### Apply Rules to Transactions")
        st.markdown("Apply all active rules to untagged transactions automatically.")

        # Service selection for rule application
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Apply to Single Service")
            service = st.selectbox(
                "Select service:",
                options=["credit_card", "bank"],
                format_func=lambda x: "Credit Card" if x == "credit_card" else "Bank",
                key="apply_service_selector"
            )

            if st.button(f"🚀 Apply All {service.replace('_', ' ').title()} Rules", key="apply_single_service"):
                tagged_count = self.rules_service.apply_all_rules(service)
                if tagged_count > 0:
                    st.success(f"✅ Tagged {tagged_count} transactions!")
                else:
                    st.info("No transactions were tagged. All may already be categorized or no rules matched.")

        with col2:
            st.markdown("#### Apply to All Services")
            st.markdown("Apply rules to both Credit Card and Bank transactions.")

            if st.button("🚀 Apply All Rules to All Services", key="apply_all_services", type="primary"):
                results = self.rules_service.apply_rules_to_all_services()
                total_tagged = sum(results.values())

                if total_tagged > 0:
                    st.success(f"✅ Tagged {total_tagged} transactions total!")
                    for service_name, count in results.items():
                        if count > 0:
                            st.info(f"  • {service_name.replace('_', ' ').title()}: {count} transactions")
                else:
                    st.info("No transactions were tagged. All may already be categorized or no rules matched.")

    def render_rule_creation_interface(self, transaction: pd.Series, service: str) -> None:
        """
        Render interface for creating rules based on a transaction.
        This method is called from TransactionsTaggingComponent.
        """
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
            # Get available operators based on field type
            available_operators = self._get_operators_for_field(field)

            # Ensure current operator is valid for the field, otherwise use first available
            current_operator = condition['operator']
            if current_operator not in available_operators:
                current_operator = available_operators[0]

            operator = st.selectbox(
                "Operator",
                options=available_operators,
                index=available_operators.index(current_operator) if current_operator in available_operators else 0,
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

    def _get_operators_for_field(self, field: str) -> List[str]:
        """Get available operators for a specific field type."""
        text_operators = [
            RuleOperators.CONTAINS.value,
            RuleOperators.EQUALS.value,
            RuleOperators.STARTS_WITH.value,
            RuleOperators.ENDS_WITH.value
        ]

        numeric_operators = [
            RuleOperators.EQUALS.value,
            RuleOperators.GREATER_THAN.value,
            RuleOperators.LESS_THAN.value,
            RuleOperators.GREATER_THAN_EQUAL.value,
            RuleOperators.LESS_THAN_EQUAL.value,
            RuleOperators.BETWEEN.value
        ]

        # Map fields to their operator types
        field_operator_map = {
            RuleFields.DESCRIPTION.value: text_operators,
            RuleFields.PROVIDER.value: text_operators,
            RuleFields.ACCOUNT_NAME.value: text_operators,
            RuleFields.ACCOUNT_NUMBER.value: text_operators,
            RuleFields.AMOUNT.value: numeric_operators
        }

        return field_operator_map.get(field, text_operators)
