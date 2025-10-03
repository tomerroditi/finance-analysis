import json
from typing import Dict, List, Literal, Optional, Any, Tuple
from datetime import datetime

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.tagging_rules_repository import TaggingRulesRepository
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import (
    RuleOperators,
    RuleFields,
    TransactionsTableFields,
)


class RuleEngine:
    """
    Engine for evaluating tagging rules against transactions.
    Contains the business logic for rule evaluation.
    """

    @staticmethod
    def evaluate_condition(transaction: pd.Series, condition: Dict[str, Any]) -> bool:
        """
        Evaluate a single condition against a transaction.

        Parameters
        ----------
        transaction : pd.Series
            The transaction to evaluate.
        condition : Dict[str, Any]
            The condition to evaluate with keys: field, operator, value.

        Returns
        -------
        bool
            True if the condition matches, False otherwise.
        """
        field = condition.get('field')
        operator = condition.get('operator')
        value = condition.get('value')

        if not all([field, operator, value is not None]):
            return False

        # Map rule fields to transaction columns
        field_mapping = {
            RuleFields.DESCRIPTION.value: TransactionsTableFields.DESCRIPTION.value,
            RuleFields.AMOUNT.value: TransactionsTableFields.AMOUNT.value,
            RuleFields.PROVIDER.value: TransactionsTableFields.PROVIDER.value,
            RuleFields.ACCOUNT_NAME.value: TransactionsTableFields.ACCOUNT_NAME.value,
            RuleFields.ACCOUNT_NUMBER.value: TransactionsTableFields.ACCOUNT_NUMBER.value,
        }

        transaction_field = field_mapping.get(field)
        if not transaction_field or transaction_field not in transaction.index:
            return False

        transaction_value = transaction[transaction_field]

        # Handle null values
        if pd.isna(transaction_value):
            return False

        # Evaluate based on operator
        if operator == RuleOperators.CONTAINS.value:
            return str(value).lower() in str(transaction_value).lower()
        elif operator == RuleOperators.EQUALS.value:
            return str(transaction_value).lower() == str(value).lower()
        elif operator == RuleOperators.STARTS_WITH.value:
            return str(transaction_value).lower().startswith(str(value).lower())
        elif operator == RuleOperators.ENDS_WITH.value:
            return str(transaction_value).lower().endswith(str(value).lower())
        elif operator == RuleOperators.GREATER_THAN.value:
            try:
                return float(transaction_value) > float(value)
            except (ValueError, TypeError):
                return False
        elif operator == RuleOperators.LESS_THAN.value:
            try:
                return float(transaction_value) < float(value)
            except (ValueError, TypeError):
                return False
        elif operator == RuleOperators.GREATER_THAN_EQUAL.value:
            try:
                return float(transaction_value) >= float(value)
            except (ValueError, TypeError):
                return False
        elif operator == RuleOperators.LESS_THAN_EQUAL.value:
            try:
                return float(transaction_value) <= float(value)
            except (ValueError, TypeError):
                return False
        elif operator == RuleOperators.BETWEEN.value:
            try:
                if isinstance(value, list) and len(value) == 2:
                    return float(value[0]) <= float(transaction_value) <= float(value[1])
                return False
            except (ValueError, TypeError):
                return False

        return False

    @staticmethod
    def evaluate_rule(transaction: pd.Series, rule: pd.Series) -> bool:
        """
        Evaluate all conditions in a rule against a transaction.
        All conditions must match (AND logic).

        Parameters
        ----------
        transaction : pd.Series
            The transaction to evaluate.
        rule : pd.Series
            The rule containing conditions to evaluate.

        Returns
        -------
        bool
            True if all conditions match, False otherwise.
        """
        try:
            conditions = json.loads(rule['conditions'])
            if not isinstance(conditions, list):
                return False

            # All conditions must match (AND logic)
            for condition in conditions:
                if not RuleEngine.evaluate_condition(transaction, condition):
                    return False

            return True
        except (json.JSONDecodeError, KeyError):
            return False


class TaggingRulesService:
    """
    Service for managing rule-based tagging operations.
    Contains business logic for rule management and application.
    """

    def __init__(self, conn: SQLConnection = None):
        self.conn = conn or get_db_connection()
        self.rules_repo = TaggingRulesRepository(self.conn)
        self.transactions_repo = TransactionsRepository(self.conn)

    def get_all_rules(self, active_only: bool = True) -> pd.DataFrame:
        """Get all rules, optionally filtered active status."""
        return self.rules_repo.get_all_rules(active_only=active_only)

    def get_rule_by_id(self, rule_id: int) -> Optional[Dict[str, Any]]:
        """Get a rule by ID and parse its conditions."""
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if rule is not None:
            rule_dict = rule.to_dict()
            try:
                rule_dict['conditions'] = json.loads(rule_dict['conditions'])
            except json.JSONDecodeError:
                rule_dict['conditions'] = []
            return rule_dict
        return None

    def add_rule(self, name: str, conditions: List[Dict[str, Any]], category: str, tag: str, priority: int = 1) -> int:
        """
        Add a new tagging rule. Alias for create_rule for backward compatibility.

        Returns
        -------
        int
            ID of the created rule.
        """
        rule_id = self.rules_repo.add_rule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
            priority=priority,
        )
        self.apply_rules()
        return rule_id

    def update_rule(self, rule_id: int, **kwargs) -> bool:
        """Update an existing rule with provided fields."""
        updated = self.rules_repo.update_rule(rule_id, **kwargs)
        if updated:
            self.apply_rules()
        return updated

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        return self.rules_repo.delete_rule(rule_id)

    def apply_rules(self) -> int:
        """
        Apply rules to all services and return counts.

        Returns
        -------
        int
            Number of transactions updated.
        """
        return self.rules_repo.apply_rules_to_transactions()

    def validate_conditions(self, conditions: List[Dict[str, Any]]) -> List[str]:
        """
        Validate rule conditions and return list of error messages.

        Parameters
        ----------
        conditions : List[Dict[str, Any]]
            Conditions to validate.

        Returns
        -------
        List[str]
            List of validation error messages. Empty if valid.
        """
        errors = []

        if not conditions:
            errors.append("At least one condition is required")
            return errors

        valid_fields = [field.value for field in RuleFields]

        # within condition issues
        for i, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                errors.append(f"Condition {i+1}: Must be a dictionary")
                continue

            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')

            if field not in valid_fields:
                errors.append(f"Condition {i+1}: Invalid field '{field}'")

            if field in valid_fields:
                valid_operators = self.get_operators_for_field(field) if field in valid_fields else []
                if operator not in valid_operators:
                    errors.append(f"Condition {i+1}: Invalid operator '{operator}', for field '{field}' select from {valid_operators}")

            if value is None:
                errors.append(f"Condition {i+1}: Value is required")
            elif operator == RuleOperators.BETWEEN.value:
                if not isinstance(value, list) or len(value) != 2:
                    errors.append(f"Condition {i+1}: Between operator requires array of 2 numbers")
                else:
                    try:
                        float(value[0])
                        float(value[1])
                    except (ValueError, TypeError):
                        errors.append(f"Condition {i+1}: Between values must be numbers")
            elif operator in [RuleOperators.GREATER_THAN.value, RuleOperators.LESS_THAN.value,
                            RuleOperators.GREATER_THAN_EQUAL.value, RuleOperators.LESS_THAN_EQUAL.value]:
                if field == RuleFields.AMOUNT.value:
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors.append(f"Condition {i+1}: Amount comparisons require numeric values")

        # cross-condition issues
        fields = [cond.get('field') for cond in conditions if isinstance(cond, dict)]
        if len(fields) != len(set(fields)):
            duplicated_fields = set([f for f in fields if fields.count(f) > 1])
            errors.append(f"Each field can only be used once in the conditions. Duplicate fields found: {duplicated_fields}")

        return errors

    def get_operators_for_field(self, field: str) -> List[str]:
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
        # TODO: make provider, account name, account number restricted to dropdowns of existing values
        field_operator_map = {
            RuleFields.DESCRIPTION.value: text_operators,
            RuleFields.PROVIDER.value: text_operators,
            RuleFields.ACCOUNT_NAME.value: text_operators,
            RuleFields.ACCOUNT_NUMBER.value: text_operators,
            RuleFields.AMOUNT.value: numeric_operators,
            RuleFields.SERVICE.value: [RuleOperators.EQUALS.value],  # special case, selecting from dropdown
        }

        return field_operator_map.get(field, text_operators)

    def test_rule_against_transactions(self, conditions: List[Dict[str, Any]], limit: int | None = None) -> (int, pd.DataFrame):
        """
        Test rule conditions against existing transactions to see what would match.

        Parameters
        ----------
        conditions : List[Dict[str, Any]]
            Rule conditions to test.
        limit : int | None
            Maximum number of results to return.

        Returns
        -------
        int
            Number of matching transactions.
        pd.DataFrame
            Transactions that would match the rule.
        """
        # TODO: simplify this with a query builder (functionality exists at repo level)
        tables = self.rules_repo._get_tables_names_for_rule_application_from_conditions(conditions)
        transactions = self.transactions_repo.get_table(tables if len(tables) == 1 else None)

        matching_transactions = []
        for _, transaction in transactions.iterrows():
            # Create a mock rule to test conditions
            mock_rule = pd.Series({'conditions': json.dumps(conditions)})
            if RuleEngine.evaluate_rule(transaction, mock_rule):
                matching_transactions.append(transaction)

        data = pd.DataFrame(matching_transactions)
        if limit is not None:
            data = data.head(limit)

        return len(matching_transactions), data
