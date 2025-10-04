import json
from typing import Dict, List, Optional, Any

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.tagging_rules_repository import TaggingRulesRepository
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import (
    RuleOperators,
    RuleFields,
    TransactionsTableFields,
    Tables,
)

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

    def get_rule_by_id(self, rule_id: int, json_load_conditions: bool = True) -> Optional[Dict[str, Any]]:
        """Get a rule by ID and parse its conditions."""
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if rule is not None:
            rule_dict = rule.to_dict()
            if json_load_conditions:
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

    def update_rule(self, rule_id: int, **kwargs) -> int:
        """Update an existing rule with provided fields."""
        updated = self.rules_repo.update_rule(rule_id, **kwargs)
        n_tagged = 0
        if updated:
            n_tagged = self.apply_rule_by_id(rule_id)
        return n_tagged

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        return self.rules_repo.delete_rule(rule_id)

    def apply_rules(self) -> int:
        """
        Apply rules (active rules only) to all services and return counts.

        This method uses a priority-based approach where higher priority rules are applied first.

        Returns
        -------
        int
            Number of transactions updated.
        """
        rules = self.rules_repo.get_all_rules(active_only=True)
        rules = rules.to_dict(orient="records")

        total_tagged = 0

        for rule in rules:
            total_tagged += self._apply_single_rule(rule)

        return total_tagged

    def apply_rule_by_id(self, rule_id: int) -> int:
        """
        Apply a single rule by ID to all services and return count of tagged transactions.

        Parameters
        ----------
        rule_id : int
            ID of the rule to apply.

        Returns
        -------
        int
            Number of transactions updated.
        """
        rule = self.get_rule_by_id(rule_id, json_load_conditions=False)
        if rule is None:
            raise ValueError(f"Rule with ID {rule_id} not found.")

        return self._apply_single_rule(rule)

    def _apply_single_rule(self, rule: Dict) -> int:
        """
        Apply a single rule to untagged transactions.

        Args:
            rule: Rule record from database

        Returns:
            Number of transactions that were tagged by this rule
        """
        conditions = json.loads(rule[self.rules_repo.conditions_col])
        where_conditions, params = self._build_rule_where_clause_conditions(conditions)
        tables = self._get_tables_names_for_rule_application_from_conditions(conditions)

        row_count = 0
        for table in tables:
            update_query = f"""
                UPDATE {table}
                SET {self.rules_repo.category_col} = :category,
                    {self.rules_repo.tag_col} = :tag
                WHERE {where_conditions} AND ({self.rules_repo.category_col} != :category OR {self.rules_repo.category_col} is null) AND ({self.rules_repo.tag_col} != :tag OR {self.rules_repo.tag_col} is null)
            """
            params = {'category': rule[self.rules_repo.category_col], 'tag': rule[self.rules_repo.tag_col], **params}
            row_count +=self.transactions_repo.update_with_query(update_query, params, service=table)

        return row_count

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
        # TODO: make account name, account number restricted to dropdowns of existing values
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
        tables = self._get_tables_names_for_rule_application_from_conditions(conditions)
        if not tables:
            raise ValueError("No transaction tables found to apply the rule.")

        all_transactions = []
        where_conditions, params = self._build_rule_where_clause_conditions(conditions)
        for table in tables:
            query = f"""
                SELECT * FROM {table}
                WHERE {where_conditions}
            """
            df = self.transactions_repo.get_table(service=table, query=query, query_params=params)
            all_transactions.append(df)

        all_transactions = pd.concat(all_transactions)
        total_count = len(all_transactions)
        if limit is not None:
            all_transactions = all_transactions.head(limit)
        return total_count, all_transactions

    @staticmethod
    def _get_tables_names_for_rule_application_from_conditions(conditions: List[Dict[str, Any]]) -> List[str]:
        """
        Determine which transaction tables to apply the rule to based on its 'service' condition.
        If no 'service' condition is found, return all transaction tables.

        Parameters:
        ----------
        conditions : List[Dict[str, Any]]
            List of rule conditions, each with 'field', 'operator', and 'value'.

        Returns:
        List[str]
            List of table names to apply the rule to. either Tables.CREDIT_CARD.value, Tables.BANK.value, or both.
        """
        tables = [Tables.CREDIT_CARD.value, Tables.BANK.value]
        for condition in conditions:
            field = condition['field']
            if field == 'service':
                if condition["value"].lower().replace(" ", "_") == "credit_card":
                    tables = [Tables.CREDIT_CARD.value]
                elif condition["value"].lower().replace(" ", "_") == "bank":
                    tables = [Tables.BANK.value]
                break

        return tables

    def _build_rule_where_clause_conditions(self, conditions: List[Dict[str, Any]]) -> (str, Dict[str, Any]):
        """
        Build complete WHERE clause and parameters for a rule.

        Parameters:
        ----------
        conditions : List[Dict[str, Any]]
            List of rule conditions, each with 'field', 'operator', and 'value'.

        Returns:
        -------
        where_conditions : List[str]
            List of SQL WHERE clause conditions.
        params : Dict[str, Any]
            Dictionary of parameters for the SQL query.
        """
        where_conditions = []
        params = {}

        # Add rule conditions
        for i, condition in enumerate(conditions):
            param_name = f'cond_{i}'
            self._add_condition_clause(where_conditions, param_name, condition, params)

        if where_conditions:
            where_conditions = ' AND '.join(where_conditions)
        else:
            raise ValueError(f"No valid conditions found in the rule. conditions: {conditions}")

        return where_conditions, params

    def _add_condition_clause(self, where_conditions: List[str], param_name: str, condition: Dict[str, Any], params: Dict[str, Any]) -> None:
        """
        Build WHERE clause and parameters for a single rule condition.

        Parameters:
        ----------
        where_conditions : List[str]
            List to append WHERE clause to (modified in place).
        param_name : str
            Unique parameter name for this condition.
        condition : Dict[str, Any]
            Rule condition with 'field', 'operator', and 'value'.
        params : Dict[str, Any]
            Dictionary to add parameters to (modified in place).
        """
        field = condition['field']
        operator = condition['operator']
        value = condition['value']

        db_field = self._map_field_to_db_column(field)
        if db_field is None:
            return  # Skip unknown/unneeded fields

        if operator == 'contains':
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f'%{value}%'
        elif operator == 'equals':
            where_conditions.append(f"{db_field} = :{param_name}")
            params[param_name] = value
        elif operator == 'starts_with':
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f'{value}%'
        elif operator == 'ends_with':
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f'%{value}'
        elif operator in ['gt', 'lt', 'gte', 'lte']:
            op_map = {'gt': '>', 'lt': '<', 'gte': '>=', 'lte': '<='}
            where_conditions.append(f"{db_field} {op_map[operator]} :{param_name}")
            params[param_name] = float(value)
        elif operator == 'between':
            if isinstance(value, list) and len(value) == 2:
                where_conditions.append(f"{db_field} BETWEEN :{param_name}_min AND :{param_name}_max")
                params[f'{param_name}_min'] = float(value[0])
                params[f'{param_name}_max'] = float(value[1])

    @staticmethod
    def _map_field_to_db_column(field: str) -> Optional[str]:
        """
        Map a rule condition field to its corresponding database column.

        Parameters:
        ----------
        field : str
            Rule condition field name.

        Returns:
        -------
        db_column : Optional[str]
            Corresponding database column name, or None if field is unknown/unneeded.
        """
        field_mapping = {
            'description': TransactionsTableFields.DESCRIPTION.value,
            'amount': TransactionsTableFields.AMOUNT.value,
            'provider': TransactionsTableFields.PROVIDER.value,
            'account_name': TransactionsTableFields.ACCOUNT_NAME.value,
            'account_number': TransactionsTableFields.ACCOUNT_NUMBER.value,
            'service': None,  # Handled separately in table selection
        }
        return field_mapping.get(field)
