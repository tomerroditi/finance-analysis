import json
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.naming_conventions import (
    TransactionsTableFields,
    Tables,
    TaggingRulesTableFields,
)


class TaggingRulesService:
    """
    Service for managing rule-based tagging operations.
    Contains business logic for rule management and application.
    """

    def __init__(self, db: Session):
        self.db = db
        self.rules_repo = TaggingRulesRepository(db)
        self.transactions_repo = TransactionsRepository(db)

    def get_all_rules(self, active_only: bool = True) -> pd.DataFrame:
        """Get all rules, optionally filtered active status."""
        return self.rules_repo.get_all_rules(active_only=active_only)

    def get_rule_by_id(
        self, rule_id: int, json_load_conditions: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a rule by ID and parse its conditions."""
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if rule is not None:
            rule_dict = rule.to_dict()
            if json_load_conditions:
                try:
                    rule_dict["conditions"] = json.loads(rule_dict["conditions"])
                except json.JSONDecodeError:
                    rule_dict["conditions"] = []
            return rule_dict
        return None

    def add_rule(
        self,
        name: str,
        conditions: List[Dict[str, Any]],
        category: str,
        tag: str,
        priority: int = 1,
    ) -> (int, int):
        """Add a new tagging rule and apply it."""
        rule_id = self.rules_repo.add_rule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
            priority=priority,
        )
        n_tagged = self.apply_rule_by_id(rule_id)
        return rule_id, n_tagged

    def update_rule(self, rule_id: int, **kwargs) -> int:
        """Update an existing rule and re-apply it."""
        updated = self.rules_repo.update_rule(rule_id, **kwargs)
        n_tagged = 0
        if updated:
            n_tagged = self.apply_rule_by_id(rule_id)
        return n_tagged

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        sucess = self.rules_repo.delete_rule(rule_id)
        if not sucess:
            raise EntityNotFoundException(f"Rule with ID {rule_id} not found")
        return sucess

    def apply_rules(self) -> int:
        """Apply all active rules."""
        rules_df = self.rules_repo.get_all_rules(active_only=True)
        rules = rules_df.to_dict(orient="records")

        total_tagged = 0
        for rule in rules:
            total_tagged += self._apply_single_rule(rule)
        return total_tagged

    def apply_rule_by_id(self, rule_id: int) -> int:
        """Apply a single rule by ID."""
        rule = self.get_rule_by_id(rule_id, json_load_conditions=False)
        if rule is None:
            raise ValueError(f"Rule with ID {rule_id} not found.")
        return self._apply_single_rule(rule)

    def _apply_single_rule(self, rule: Dict) -> int:
        """Apply a single rule to untagged transactions."""
        conditions = json.loads(rule[TaggingRulesTableFields.CONDITIONS.value])
        where_conditions, params = self._build_rule_where_clause_conditions(conditions)
        tables = self._get_tables_names_for_rule_application_from_conditions(conditions)

        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value

        row_count = 0
        for table in tables:
            update_query = f"""
                UPDATE {table}
                SET {category_col} = :category,
                    {tag_col} = :tag
                WHERE {where_conditions} AND ({category_col} != :category OR {category_col} is null) AND ({tag_col} != :tag OR {tag_col} is null)
            """
            update_params = {
                "category": rule[TaggingRulesTableFields.CATEGORY.value],
                "tag": rule[TaggingRulesTableFields.TAG.value],
                **params,
            }
            row_count += self.transactions_repo.update_with_query(
                update_query, update_params, service=table
            )
        return row_count

    def test_rule_against_transactions(
        self, conditions: List[Dict[str, Any]], limit: int | None = None
    ) -> (int, pd.DataFrame):
        """Test rule conditions against existing transactions."""
        tables = self._get_tables_names_for_rule_application_from_conditions(conditions)
        if not tables:
            return 0, pd.DataFrame()

        all_transactions = []
        where_conditions, params = self._build_rule_where_clause_conditions(conditions)
        for table in tables:
            query = f"SELECT * FROM {table} WHERE {where_conditions}"
            df = self.transactions_repo.get_table(
                service=table, query=query, query_params=params
            )
            all_transactions.append(df)

        if not all_transactions:
            return 0, pd.DataFrame()

        full_df = pd.concat(all_transactions, ignore_index=True)
        total_count = len(full_df)
        if limit is not None:
            full_df = full_df.head(limit)
        return total_count, full_df

    @staticmethod
    def _get_tables_names_for_rule_application_from_conditions(
        conditions: List[Dict[str, Any]],
    ) -> List[str]:
        tables = [Tables.CREDIT_CARD.value, Tables.BANK.value]
        for condition in conditions:
            if condition.get("field") == "service":
                val = str(condition.get("value", "")).lower().replace(" ", "_")
                if val == "credit_card":
                    tables = [Tables.CREDIT_CARD.value]
                elif val == "bank":
                    tables = [Tables.BANK.value]
                break
        return tables

    def _build_rule_where_clause_conditions(
        self, conditions: List[Dict[str, Any]]
    ) -> (str, Dict[str, Any]):
        where_conditions = []
        params = {}
        for i, condition in enumerate(conditions):
            param_name = f"cond_{i}"
            self._add_condition_clause(where_conditions, param_name, condition, params)
        if not where_conditions:
            raise ValueError(f"No valid conditions found in the rule.")
        return " AND ".join(where_conditions), params

    def _add_condition_clause(
        self,
        where_conditions: List[str],
        param_name: str,
        condition: Dict[str, Any],
        params: Dict[str, Any],
    ) -> None:
        field = condition["field"]
        operator = condition["operator"]
        value = condition["value"]
        db_field = self._map_field_to_db_column(field)
        if db_field is None:
            return

        if operator == "contains":
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f"%{value}%"
        elif operator == "equals":
            where_conditions.append(f"{db_field} = :{param_name}")
            params[param_name] = value
        elif operator == "starts_with":
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f"{value}%"
        elif operator == "ends_with":
            where_conditions.append(f"{db_field} LIKE :{param_name}")
            params[param_name] = f"%{value}"
        elif operator in ["gt", "lt", "gte", "lte"]:
            op_map = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
            where_conditions.append(f"{db_field} {op_map[operator]} :{param_name}")
            params[param_name] = float(value)
        elif operator == "between":
            if isinstance(value, list) and len(value) == 2:
                where_conditions.append(
                    f"{db_field} BETWEEN :{param_name}_min AND :{param_name}_max"
                )
                params[f"{param_name}_min"] = float(value[0])
                params[f"{param_name}_max"] = float(value[1])

    @staticmethod
    def _map_field_to_db_column(field: str) -> Optional[str]:
        field_mapping = {
            "description": TransactionsTableFields.DESCRIPTION.value,
            "amount": TransactionsTableFields.AMOUNT.value,
            "provider": TransactionsTableFields.PROVIDER.value,
            "account_name": TransactionsTableFields.ACCOUNT_NAME.value,
            "account_number": TransactionsTableFields.ACCOUNT_NUMBER.value,
            "service": None,
        }
        return field_mapping.get(field)
