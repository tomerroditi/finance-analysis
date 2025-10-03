import json
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.sql import text
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import (
    Tables,
    TaggingRulesTableFields,
    TransactionsTableFields,
)


class TaggingRulesRepository:
    """
    Repository for basic CRUD operations on tagging rules data.
    Contains only data access logic, no business logic.
    """
    table = Tables.TAGGING_RULES.value
    id_col = TaggingRulesTableFields.ID.value
    name_col = TaggingRulesTableFields.NAME.value
    priority_col = TaggingRulesTableFields.PRIORITY.value
    conditions_col = TaggingRulesTableFields.CONDITIONS.value
    category_col = TaggingRulesTableFields.CATEGORY.value
    tag_col = TaggingRulesTableFields.TAG.value
    is_active_col = TaggingRulesTableFields.IS_ACTIVE.value
    created_date_col = TaggingRulesTableFields.CREATED_DATE.value

    def __init__(self, conn: SQLConnection):
        self.conn = conn
        self.assure_table_exists()

    def assure_table_exists(self):
        """Create the tagging rules table if it doesn't exist"""
        with self.conn.session as s:
            s.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS {self.table} ('
                    f'{self.id_col} INTEGER PRIMARY KEY AUTOINCREMENT, '
                    f'{self.name_col} TEXT NOT NULL, '
                    f'{self.priority_col} INTEGER DEFAULT 1, '
                    f'{self.conditions_col} TEXT NOT NULL, '
                    f'{self.category_col} TEXT NOT NULL, '
                    f'{self.tag_col} TEXT NOT NULL, '
                    f'{self.is_active_col} INTEGER DEFAULT 1, '
                    f'{self.created_date_col} TEXT DEFAULT CURRENT_TIMESTAMP'
                    f');'
                )
            )
            s.commit()

    def get_all_rules(self, active_only: bool = True) -> pd.DataFrame:
        """Get all tagging rules, optionally filtered by active status"""
        where_clauses = []
        params = {}

        if active_only:
            where_clauses.append(f'{self.is_active_col} = 1')

        where_clause = f" WHERE {' AND '.join(where_clauses)} " if where_clauses else " "

        with self.conn.session as s:
            query = f'SELECT * FROM {self.table}{where_clause}ORDER BY {self.priority_col} DESC, {self.id_col};'
            result = s.execute(text(query), params).fetchall()
        return pd.DataFrame(result)

    def get_rule_by_id(self, rule_id: int) -> Optional[pd.Series]:
        """Get a specific rule by ID"""
        with self.conn.session as s:
            query = f'SELECT * FROM {self.table} WHERE {self.id_col} = :id;'
            params = {'id': int(rule_id)}
            result = s.execute(text(query), params).fetchall()

        # Convert to DataFrame after fetching
        df_result = pd.DataFrame(result)

        if not df_result.empty:
            return df_result.iloc[0]
        return None

    def add_rule(self, name: str, conditions: List[Dict[str, Any]], category: str, tag: str, priority: int = 1, is_active: bool = True) -> int:
        """Add a new tagging rule to the database. Returns the new rule ID."""
        with self.conn.session as s:
            params = {
                'name': name,
                'priority': priority,
                'conditions': json.dumps(conditions),
                'category': category,
                'tag': tag,
                'is_active': 1 if is_active else 0,
                'created_date': datetime.now().isoformat()
            }

            query = sa.text(f"""
                INSERT INTO {self.table} ({self.name_col}, {self.priority_col}, {self.conditions_col}, 
                                         {self.category_col}, {self.tag_col}, {self.is_active_col}, {self.created_date_col})
                VALUES (:name, :priority, :conditions, :category, :tag, :is_active, :created_date)
            """)
            result = s.execute(query, params)
            s.commit()
            return result.lastrowid

    def update_rule(self, rule_id: int, name: str = None, conditions: List[Dict[str, Any]] = None, category: str = None, tag: str = None, priority: int = None, is_active: bool = None) -> bool:
        """Update an existing rule. Only updates provided fields."""
        updates = []
        params = {}

        if name is not None:
            updates.append(f'{self.name_col} = :name')
            params['name'] = name

        if conditions is not None:
            updates.append(f'{self.conditions_col} = :conditions')
            params['conditions'] = json.dumps(conditions)

        if category is not None:
            updates.append(f'{self.category_col} = :category')
            params['category'] = category

        if tag is not None:
            updates.append(f'{self.tag_col} = :tag')
            params['tag'] = tag

        if priority is not None:
            updates.append(f'{self.priority_col} = :priority')
            params['priority'] = priority

        if is_active is not None:
            updates.append(f'{self.is_active_col} = :is_active')
            params['is_active'] = 1 if is_active else 0

        if not updates:
            return False

        with self.conn.session as s:
            query = sa.text(f"UPDATE {self.table} SET {', '.join(updates)} WHERE {self.id_col} = :id")
            result = s.execute(query, {**params, 'id': int(rule_id)})
            s.commit()
            return result.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID"""
        with self.conn.session as s:
            query = sa.text(f"DELETE FROM {self.table} WHERE {self.id_col} = :id")
            result = s.execute(query, {'id': int(rule_id)})
            s.commit()
            return result.rowcount > 0

    def delete_rules_by_category_and_tag(self, category: str, tag: str) -> int:
        """Delete all rules with the specified category and tag. Returns number of deleted rules."""
        with self.conn.session as s:
            query = sa.text(f"""
                DELETE FROM {self.table}
                WHERE {self.category_col} = :category AND {self.tag_col} = :tag
            """)
            result = s.execute(query, {'category': category, 'tag': tag})
            s.commit()
            return result.rowcount

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> int:
        """Update category for all rules with the specified old_category and tag. Returns number of updated rules."""
        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :new_category
                WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
            """)
            result = s.execute(query, {
                'new_category': new_category,
                'old_category': old_category,
                'tag': tag
            })
            s.commit()
            return result.rowcount

    def delete_rules_by_category(self, category: str) -> int:
        """Delete all rules with the specified category. Returns number of deleted rules."""
        with self.conn.session as s:
            query = sa.text(f"DELETE FROM {self.table} WHERE {self.category_col} = :category")
            result = s.execute(query, {'category': category})
            s.commit()
            return result.rowcount

    def apply_rules_to_transactions(self) -> int:
        """
        Apply all active rules to untagged transactions.
        Returns the number of transactions that were tagged.

        This method uses a priority-based approach where higher priority rules are applied first.
        """
        with self.conn.session as s:
            rules_query = f"""
                SELECT * FROM {self.table} 
                WHERE {self.is_active_col} = 1
                ORDER BY {self.priority_col} DESC, {self.id_col}
            """
            rules_result = s.execute(text(rules_query))
            rules = list(rules_result.fetchall())
            total_tagged = 0

            for rule in rules:
                tagged_count = self._apply_single_rule(s, rule)
                total_tagged += tagged_count

            s.commit()
            return total_tagged

    def _apply_single_rule(self, session: Session, rule: sa.Row) -> int:
        """
        Apply a single rule to untagged transactions.

        Args:
            session: Database session
            rule: Rule record from database

        Returns:
            Number of transactions that were tagged by this rule
        """

        rule = rule._mapping
        conditions = json.loads(rule[self.conditions_col])
        where_conditions, params = self._build_rule_where_clause_conditions(conditions)
        tables = self._get_tables_names_for_rule_application_from_conditions(conditions)

        row_count = 0
        for table in tables:
            update_query = f"""
                UPDATE {table}
                SET {TransactionsTableFields.CATEGORY.value} = :category,
                    {TransactionsTableFields.TAG.value} = :tag
                WHERE {where_conditions}
            """

            result = session.execute(text(update_query), {"category": rule[self.category_col], "tag": rule[self.tag_col], **params})
            row_count += result.rowcount
        return row_count

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
