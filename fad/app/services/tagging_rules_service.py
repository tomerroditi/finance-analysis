import json
from typing import Dict, List, Literal, Optional, Any, Tuple
from datetime import datetime

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.tagging_rules_repository import TaggingRulesRepository
from fad.app.data_access.tagging_repository import AutoTaggerRepository
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

    @staticmethod
    def find_matching_rule(transaction: pd.Series, rules: pd.DataFrame) -> Optional[pd.Series]:
        """
        Find the first matching rule for a transaction based on priority.

        Parameters
        ----------
        transaction : pd.Series
            The transaction to find a rule for.
        rules : pd.DataFrame
            DataFrame of rules sorted by priority (highest first).

        Returns
        -------
        Optional[pd.Series]
            The first matching rule, or None if no rule matches.
        """
        for _, rule in rules.iterrows():
            if RuleEngine.evaluate_rule(transaction, rule):
                return rule
        return None


class TaggingRulesService:
    """
    Service for managing rule-based tagging operations.
    Contains business logic for rule management and application.
    """

    def __init__(self, conn: SQLConnection = None):
        self.conn = conn or get_db_connection()
        self.rules_repo = TaggingRulesRepository(self.conn)
        self.transactions_repo = TransactionsRepository(self.conn)
        self.auto_tagger_repo = AutoTaggerRepository(self.conn)

    def get_all_rules(self, service: Optional[Literal['credit_card', 'bank']] = None) -> pd.DataFrame:
        """Get all active rules, optionally filtered by service."""
        return self.rules_repo.get_all_rules(service=service, active_only=True)

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

    def create_rule(self, name: str, conditions: List[Dict[str, Any]], category: str, tag: str,
                   service: Literal['credit_card', 'bank'], priority: int = 1,
                   account_number: Optional[str] = None) -> int:
        """
        Create a new tagging rule.

        Parameters
        ----------
        name : str
            Human-readable name for the rule.
        conditions : List[Dict[str, Any]]
            List of conditions that must all match.
        category : str
            Category to assign when rule matches.
        tag : str
            Tag to assign when rule matches.
        service : Literal['credit_card', 'bank']
            Service type this rule applies to.
        priority : int
            Rule priority (higher number = higher priority).
        account_number : Optional[str]
            Account number for bank rules.

        Returns
        -------
        int
            ID of the created rule.
        """
        return self.rules_repo.add_rule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
            service=service,
            priority=priority,
            account_number=account_number
        )

    def update_rule(self, rule_id: int, **kwargs) -> bool:
        """Update an existing rule with provided fields."""
        return self.rules_repo.update_rule(rule_id, **kwargs)

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        return self.rules_repo.delete_rule(rule_id)

    def apply_rules_to_transactions(self, service: Literal['credit_card', 'bank']) -> int:
        """
        Apply all active rules to untagged transactions.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            Service to apply rules to.

        Returns
        -------
        int
            Number of transactions that were tagged.
        """
        return self.rules_repo.apply_rules_to_transactions(service)

    def apply_rules_to_all_services(self) -> Dict[str, int]:
        """
        Apply rules to all services and return counts.

        Returns
        -------
        Dict[str, int]
            Dictionary with service names as keys and tagged counts as values.
        """
        results = {}
        for service in ['credit_card', 'bank']:
            results[service] = self.apply_rules_to_transactions(service)
        return results

    def test_rule_against_transactions(self, conditions: List[Dict[str, Any]],
                                     service: Literal['credit_card', 'bank'],
                                     account_number: Optional[str] = None,
                                     limit: int = 100) -> pd.DataFrame:
        """
        Test rule conditions against existing transactions to see what would match.

        Parameters
        ----------
        conditions : List[Dict[str, Any]]
            Rule conditions to test.
        service : Literal['credit_card', 'bank']
            Service to test against.
        account_number : Optional[str]
            Account number filter for bank transactions.
        limit : int
            Maximum number of results to return.

        Returns
        -------
        pd.DataFrame
            Transactions that would match the rule.
        """
        transactions = self.transactions_repo.get_table(service)

        if account_number and service == 'bank':
            account_col = TransactionsTableFields.ACCOUNT_NUMBER.value
            transactions = transactions[transactions[account_col] == account_number]

        matching_transactions = []

        for _, transaction in transactions.iterrows():
            # Create a mock rule to test conditions
            mock_rule = pd.Series({'conditions': json.dumps(conditions)})
            if RuleEngine.evaluate_rule(transaction, mock_rule):
                matching_transactions.append(transaction)
                if len(matching_transactions) >= limit:
                    break

        return pd.DataFrame(matching_transactions) if matching_transactions else pd.DataFrame()

    def get_untagged_transactions(self, service: Literal['credit_card', 'bank'],
                                 account_number: Optional[str] = None) -> pd.DataFrame:
        """
        Get transactions that don't have categories assigned.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            Service to get transactions from.
        account_number : Optional[str]
            Account number filter for bank transactions.

        Returns
        -------
        pd.DataFrame
            Untagged transactions.
        """
        transactions = self.transactions_repo.get_table(service)
        category_col = TransactionsTableFields.CATEGORY.value

        # Filter for untagged transactions
        untagged = transactions[transactions[category_col].isna()]

        if account_number and service == 'bank':
            account_col = TransactionsTableFields.ACCOUNT_NUMBER.value
            untagged = untagged[untagged[account_col] == account_number]

        return untagged

    def migrate_from_auto_tagger(self) -> int:
        """
        Migrate existing auto tagger rules to the new rule-based system.

        Returns
        -------
        int
            Number of rules migrated.
        """
        auto_tagger_rules = self.auto_tagger_repo.get_table()
        migrated_count = 0

        for _, rule in auto_tagger_rules.iterrows():
            # Convert simple name-based rule to new condition format
            conditions = [{
                'field': RuleFields.DESCRIPTION.value,
                'operator': RuleOperators.EQUALS.value,
                'value': rule[self.auto_tagger_repo.name_col]
            }]

            try:
                self.create_rule(
                    name=f"Migrated: {rule[self.auto_tagger_repo.name_col]}",
                    conditions=conditions,
                    category=rule[self.auto_tagger_repo.category_col],
                    tag=rule[self.auto_tagger_repo.tag_col],
                    service=rule[self.auto_tagger_repo.service_col],
                    priority=1,
                    account_number=rule[self.auto_tagger_repo.account_number_col]
                )
                migrated_count += 1
            except Exception:
                # Skip rules that fail to migrate
                continue

        return migrated_count

    def get_rule_suggestions(self, transaction: pd.Series,
                           service: Literal['credit_card', 'bank']) -> List[Dict[str, Any]]:
        """
        Suggest rule conditions based on a transaction.

        Parameters
        ----------
        transaction : pd.Series
            Transaction to base suggestions on.
        service : Literal['credit_card', 'bank']
            Service type.

        Returns
        -------
        List[Dict[str, Any]]
            List of suggested conditions.
        """
        suggestions = []

        # Description-based suggestions
        desc_col = TransactionsTableFields.DESCRIPTION.value
        if desc_col in transaction.index and pd.notna(transaction[desc_col]):
            desc = str(transaction[desc_col])

            # Exact match
            suggestions.append({
                'field': RuleFields.DESCRIPTION.value,
                'operator': RuleOperators.EQUALS.value,
                'value': desc,
                'description': f'Description equals "{desc}"'
            })

            # Contains (for partial matches)
            words = desc.split()
            if len(words) > 1:
                # Suggest using first few words
                partial = ' '.join(words[:2])
                suggestions.append({
                    'field': RuleFields.DESCRIPTION.value,
                    'operator': RuleOperators.CONTAINS.value,
                    'value': partial,
                    'description': f'Description contains "{partial}"'
                })

        # Amount-based suggestions
        amount_col = TransactionsTableFields.AMOUNT.value
        if amount_col in transaction.index and pd.notna(transaction[amount_col]):
            amount = float(transaction[amount_col])

            # Exact amount
            suggestions.append({
                'field': RuleFields.AMOUNT.value,
                'operator': RuleOperators.EQUALS.value,
                'value': amount,
                'description': f'Amount equals {amount}'
            })

            # Amount range (±10%)
            margin = abs(amount * 0.1)
            suggestions.append({
                'field': RuleFields.AMOUNT.value,
                'operator': RuleOperators.BETWEEN.value,
                'value': [amount - margin, amount + margin],
                'description': f'Amount between {amount - margin:.2f} and {amount + margin:.2f}'
            })

        # Provider-based suggestions
        provider_col = TransactionsTableFields.PROVIDER.value
        if provider_col in transaction.index and pd.notna(transaction[provider_col]):
            provider = str(transaction[provider_col])
            suggestions.append({
                'field': RuleFields.PROVIDER.value,
                'operator': RuleOperators.EQUALS.value,
                'value': provider,
                'description': f'Provider equals "{provider}"'
            })

        return suggestions

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
        valid_operators = [op.value for op in RuleOperators]

        for i, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                errors.append(f"Condition {i+1}: Must be a dictionary")
                continue

            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')

            if field not in valid_fields:
                errors.append(f"Condition {i+1}: Invalid field '{field}'")

            if operator not in valid_operators:
                errors.append(f"Condition {i+1}: Invalid operator '{operator}'")

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

        return errors
