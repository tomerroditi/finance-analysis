import json
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.errors import BadRequestException, EntityNotFoundException
from backend.naming_conventions import Tables, TransactionsTableFields
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import TransactionsRepository


class TaggingRulesService:
    """
    Service for managing rule-based tagging operations with recursive logic.
    """

    def __init__(self, db: Session):
        self.db = db
        self.rules_repo = TaggingRulesRepository(db)
        self.transactions_repo = TransactionsRepository(db)

    def get_all_rules(self) -> pd.DataFrame:
        """Get all rules."""
        return self.rules_repo.get_all_rules()

    def add_rule(
        self,
        name: str,
        conditions: Dict[str, Any],
        category: str,
        tag: str,
    ) -> Tuple[int, int]:
        """
        Add a new tagging rule with integrity and conflict checks.
        """
        # 1. Integrity Check
        self.validate_rule_integrity(conditions)

        # 2. Conflict Check
        self.check_conflicts(conditions, category, tag)

        # 3. Create Rule
        rule_id = self.rules_repo.add_rule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
        )

        # 4. Apply immediately
        n_tagged = self.apply_rule_by_id(rule_id)
        return rule_id, n_tagged

    def _normalize_conditions(self, conditions: Any) -> Dict[str, Any]:
        """
        Normalize legacy condition formats to the new recursive dict format.
        - List format: [...] -> {"type": "AND", "subconditions": [...]}
        - Simple dict: {"field": ...} -> {"type": "CONDITION", ...}
        - Recursive dict: {"type": "AND", "subconditions": [...]} (unchanged)
        """
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except:
                # Fallback if invalid JSON string (shouldn't happen with JSON column)
                return {
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": str(conditions),
                }

        if isinstance(conditions, list):
            # Legacy list of conditions -> AND group
            return {
                "type": "AND",
                "subconditions": [self._normalize_conditions(c) for c in conditions],
            }

        if isinstance(conditions, dict):
            if "type" in conditions:
                # Already new format, but recursively normalize subconditions if any
                if conditions["type"] in ["AND", "OR"]:
                    conditions["subconditions"] = [
                        self._normalize_conditions(c)
                        for c in conditions.get("subconditions", [])
                    ]
                return conditions
            else:
                # Single condition dict without 'type'
                return {
                    "type": "CONDITION",
                    "field": conditions.get("field", "description"),
                    "operator": conditions.get("operator", "contains"),
                    "value": conditions.get("value", ""),
                }

        # Last resort fallback
        return {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "",
        }

    def update_rule(self, rule_id: int, **kwargs) -> int:
        """
        Update an existing rule with validation and conflict checks.
        """
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if not rule:
            raise EntityNotFoundException(f"Rule {rule_id} not found")

        # Determine new values or keep existing
        new_conditions = kwargs.get("conditions", rule.conditions)
        new_category = kwargs.get("category", rule.category)
        new_tag = kwargs.get("tag", rule.tag)

        if "conditions" in kwargs:
            self.validate_rule_integrity(new_conditions)

        # Check conflicts excluding self (pass rule_id to exclude)
        self.check_conflicts(
            new_conditions, new_category, new_tag, exclude_rule_id=rule_id
        )

        updated = self.rules_repo.update_rule(rule_id, **kwargs)

        n_tagged = 0
        if updated:
            n_tagged = self.apply_rule_by_id(rule_id)

        return n_tagged

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule."""
        success = self.rules_repo.delete_rule(rule_id)
        if not success:
            raise EntityNotFoundException(f"Rule {rule_id} not found")
        return success

    def apply_rules(self, overwrite: bool = True) -> int:
        """
        Apply all active rules to transactions.
        """
        result = self.rules_repo.get_all_rules()
        rules = result.to_dict(orient="records")

        # Use a set to track unique (table, id) pairs for accurate counting
        modified_transactions = set()
        for rule in rules:
            modified = self._apply_single_rule_returning_ids(rule, overwrite=overwrite)
            modified_transactions.update(modified)

        return len(modified_transactions)

    def apply_rule_by_id(self, rule_id: int, overwrite: bool = True) -> int:
        """Apply a single rule by ID."""
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if not rule:
            raise EntityNotFoundException(f"Rule {rule_id} not found")
        return self._apply_single_rule(rule.__dict__, overwrite=overwrite)

    def validate_rule_integrity(self, conditions: Dict[str, Any]):
        """
        Validates that conditions matches field types.
        e.g. 'amount' must be numeric, 'date' must be valid date format,
        operators must match type.
        """
        conditions = self._normalize_conditions(conditions)
        if conditions.get("type") in ["AND", "OR"]:
            subconditions = conditions.get("subconditions", [])
            if not subconditions:
                raise BadRequestException("Group must have subconditions")
            for sub in subconditions:
                self.validate_rule_integrity(sub)
            return

        if conditions.get("type") == "CONDITION":
            field = conditions.get("field")
            operator = conditions.get("operator")
            value = conditions.get("value")

            if not field or not operator:
                raise BadRequestException("Condition missing field or operator")

            # Type Validation Logic
            valid_text_ops = ["contains", "equals", "starts_with", "ends_with"]
            valid_num_ops = ["gt", "lt", "gte", "lte", "equals", "between"]

            text_fields = ["description", "account_name", "provider", "service"]
            num_fields = ["amount"]

            if field in num_fields:
                if operator not in valid_num_ops:
                    raise BadRequestException(
                        f"Operator '{operator}' not valid for numeric field '{field}'"
                    )
                if operator == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        raise BadRequestException(
                            "Value for between must be list of 2 numbers"
                        )
                    try:
                        float(value[0])
                        float(value[1])
                    except ValueError:
                        raise BadRequestException(
                            "Values for numeric field must be numbers"
                        )
                else:
                    try:
                        float(value)
                    except ValueError:
                        raise BadRequestException(
                            f"Value '{value}' must be a number for field '{field}'"
                        )

            if field in text_fields:
                if operator not in valid_text_ops:
                    raise BadRequestException(
                        f"Operator '{operator}' not valid for text field '{field}'"
                    )

    def check_conflicts(
        self,
        conditions: Dict[str, Any],
        category: str,
        tag: str,
        exclude_rule_id: Optional[int] = None,
    ):
        """
        Checks if the new rule overlaps with any EXISTING rule on ANY transaction,
        AND matches to a DIFFERENT category/tag.
        """
        conditions = self._normalize_conditions(conditions)
        # 1. Get query for this rule
        where_clause, params = self._build_recursive_where_clause(conditions)
        if not where_clause:
            return

        # We need to check against ALL tables that this rule could apply to
        tables = self._get_tables_names_for_conditions(conditions)

        matching_tx_ids_by_table = {}

        for table in tables:
            # Find IDs of transactions matched by this NEW rule
            query = f"SELECT id FROM {table} WHERE {where_clause}"
            df = self.transactions_repo.get_table(
                service=table, query=query, query_params=params
            )
            if not df.empty:
                matching_tx_ids_by_table[table] = set(df["id"].tolist())

        if not any(matching_tx_ids_by_table.values()):
            return  # No transactions match this rule, so no conflict possible yet

        # 2. Get all OTHER rules
        other_rules_df = self.rules_repo.get_all_rules()
        if exclude_rule_id:
            other_rules_df = other_rules_df[other_rules_df["id"] != exclude_rule_id]

        other_rules = other_rules_df.to_dict(orient="records")

        for rule in other_rules:
            # Optimization: If category/tag are EXACTLY same, overlap is allowed (redundant but safe)
            if rule["category"] == category and rule["tag"] == tag:
                continue

            # Check if this EXISTING rule matches any of our transactions
            rule_conds = rule["conditions"]
            if isinstance(rule_conds, str):
                # Handle legacy/stringified logic if any (though we aim to replace)
                try:
                    rule_conds = json.loads(rule_conds)
                except:
                    continue

            r_where, r_params = self._build_recursive_where_clause(rule_conds)
            r_tables = self._get_tables_names_for_conditions(rule_conds)

            for table in r_tables:
                if table not in matching_tx_ids_by_table:
                    continue

                ids_to_check = list(matching_tx_ids_by_table[table])
                if not ids_to_check:
                    continue

                # Check overlap using SQL for efficiency
                # SELECT count(*) FROM table WHERE id IN (...) AND (rule_where_clause)
                # Batch IDs if too many
                batch_size = 900
                for i in range(0, len(ids_to_check), batch_size):
                    batch = ids_to_check[i : i + batch_size]
                    id_list = ",".join(map(str, batch))

                    check_query = f"SELECT count(*) as count FROM {table} WHERE id IN ({id_list}) AND ({r_where})"
                    # Combine params
                    combined_params = {**r_params}

                    res = self.db.execute(text(check_query), combined_params).scalar()
                    if res > 0:
                        raise BadRequestException(
                            f"Conflict detected: This rule matches transactions that are also matched by existing rule '{rule['name']}' "
                            f"which assigns a different tag ('{rule['category']} - {rule['tag']}')."
                        )

    def _apply_single_rule(self, rule: Dict[str, Any], overwrite: bool = True) -> int:
        """Legacy wrapper returning count."""
        ids = self._apply_single_rule_returning_ids(rule, overwrite=overwrite)
        return len(ids)

    def _apply_single_rule_returning_ids(
        self, rule: Dict[str, Any], overwrite: bool = True
    ) -> Set[Tuple[str, int]]:
        """
        Apply a single rule to transactions and return set of (table, unique_id) pairs updated.
        """
        conditions = self._normalize_conditions(rule["conditions"])
        where_conditions, params = self._build_recursive_where_clause(conditions)
        tables = self._get_tables_names_for_conditions(conditions)

        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value

        modified_pairs = set()
        for table in tables:
            # 1. Identify which rows SHOULD be updated
            # This avoids blind updates and helps us return the exact set of changed IDs
            extra_conditions = ""
            if not overwrite:
                extra_conditions = f" AND {category_col} IS NULL"
            else:
                # Optimized overwrite: only update if different
                extra_conditions = f" AND ({category_col} IS NOT :category OR {tag_col} IS NOT :tag OR {category_col} IS NULL)"

            # Find IDs first
            find_query = f"SELECT unique_id FROM {table} WHERE {where_conditions}{extra_conditions}"
            find_params = {
                "category": rule["category"],
                "tag": rule["tag"],
                **params,
            }

            ids_df = self.transactions_repo.get_table(
                service=table, query=find_query, query_params=find_params
            )
            if ids_df.empty:
                continue

            ids_to_update = ids_df["unique_id"].tolist()

            # 2. Perform the update
            update_query = f"""
                UPDATE {table}
                SET {category_col} = :category,
                    {tag_col} = :tag
                WHERE unique_id IN ({",".join(map(str, ids_to_update))})
            """
            self.transactions_repo.update_with_query(
                update_query,
                {"category": rule["category"], "tag": rule["tag"]},
                service=table,
            )

            for uid in ids_to_update:
                modified_pairs.add((table, uid))

        return modified_pairs

    def _build_recursive_where_clause(
        self, condition_node: Dict[str, Any], param_prefix: str = "p"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Recursively builds WHERE clause from condition tree.
        """
        c_type = condition_node.get("type")

        if c_type == "AND" or c_type == "OR":
            subconditions = condition_node.get("subconditions", [])
            if not subconditions:
                return "1=1", {}  # Empty group

            clauses = []
            all_params = {}
            for i, sub in enumerate(subconditions):
                sub_prefix = f"{param_prefix}_{i}"
                clause, params = self._build_recursive_where_clause(sub, sub_prefix)
                clauses.append(f"({clause})")
                all_params.update(params)

            join_op = " AND " if c_type == "AND" else " OR "
            return join_op.join(clauses), all_params

        elif c_type == "CONDITION":
            return self._build_single_condition(condition_node, param_prefix)

        return "1=0", {}  # Fallback

    def _build_single_condition(
        self, condition: Dict[str, Any], param_name: str
    ) -> Tuple[str, Dict[str, Any]]:
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")

        db_field = self._map_field_to_db_column(field)
        if not db_field:
            return "1=1", {}  # Ignored field

        params = {}
        clause = ""

        if operator == "contains":
            clause = f"{db_field} LIKE :{param_name}"
            params[param_name] = f"%{value}%"
        elif operator == "equals":
            clause = f"{db_field} = :{param_name}"
            params[param_name] = value
        elif operator == "starts_with":
            clause = f"{db_field} LIKE :{param_name}"
            params[param_name] = f"{value}%"
        elif operator == "ends_with":
            clause = f"{db_field} LIKE :{param_name}"
            params[param_name] = f"%{value}"
        elif operator in ["gt", "lt", "gte", "lte"]:
            op_map = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
            clause = f"{db_field} {op_map[operator]} :{param_name}"
            params[param_name] = float(value)
        elif operator == "between":
            clause = f"{db_field} BETWEEN :{param_name}_min AND :{param_name}_max"
            params[f"{param_name}_min"] = float(value[0])
            params[f"{param_name}_max"] = float(value[1])

        return clause, params

    def _map_field_to_db_column(self, field: str) -> Optional[str]:
        field_mapping = {
            "description": TransactionsTableFields.DESCRIPTION.value,
            "amount": TransactionsTableFields.AMOUNT.value,
            "provider": TransactionsTableFields.PROVIDER.value,
            "account_name": TransactionsTableFields.ACCOUNT_NAME.value,
            "service": None,  # Handled by table selection
        }
        return field_mapping.get(field)

    def _get_tables_names_for_conditions(self, conditions: Dict[str, Any]) -> List[str]:
        """
        Determine which tables to apply based on 'service' fields in conditions.
        Traverses the tree to find any 'service' restrictions.
        Default: All tables.
        """
        # Simple traversal to find service constraints.
        # This is a heuristic: if ANY condition says service=credit_card, we limit to credit_card.
        # If strict logic is needed (e.g. service=bank OR service=card), we might need robust logic.
        # For now, let's collect all requested services.

        services_found = set()
        self._collect_services(conditions, services_found)

        tables = []
        if not services_found:
            return [Tables.CREDIT_CARD.value, Tables.BANK.value]

        if "credit_card" in services_found:
            tables.append(Tables.CREDIT_CARD.value)
        if "bank" in services_found:
            tables.append(Tables.BANK.value)

        return tables

    def _collect_services(self, node: Dict[str, Any], services: Set[str]):
        if node.get("type") in ["AND", "OR"]:
            for sub in node.get("subconditions", []):
                self._collect_services(sub, services)
        elif node.get("type") == "CONDITION":
            if node.get("field") == "service" and node.get("operator") == "equals":
                val = str(node.get("value")).lower().replace(" ", "_")
                services.add(val)
