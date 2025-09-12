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
    service_col = TaggingRulesTableFields.SERVICE.value
    account_number_col = TaggingRulesTableFields.ACCOUNT_NUMBER.value
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
                    f'{self.service_col} TEXT NOT NULL, '
                    f'{self.account_number_col} TEXT, '
                    f'{self.is_active_col} INTEGER DEFAULT 1, '
                    f'{self.created_date_col} TEXT DEFAULT CURRENT_TIMESTAMP'
                    f');'
                )
            )
            s.commit()

    def get_all_rules(self, service: Optional[Literal['credit_card', 'bank']] = None,
                      active_only: bool = True) -> pd.DataFrame:
        """Get all tagging rules, optionally filtered by service and active status"""
        where_clauses = []
        params = {}

        if service:
            where_clauses.append(f'{self.service_col} = :service')
            params['service'] = service

        if active_only:
            where_clauses.append(f'{self.is_active_col} = 1')

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with self.conn.session as s:
            query = f'SELECT * FROM {self.table} {where_clause} ORDER BY {self.priority_col} DESC, {self.id_col};'
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

    def add_rule(self, name: str, conditions: List[Dict[str, Any]], category: str, tag: str,
                 service: Literal['credit_card', 'bank'], priority: int = 1,
                 account_number: Optional[str] = None, is_active: bool = True) -> int:
        """Add a new tagging rule to the database. Returns the new rule ID."""
        if service == "bank" and account_number is None:
            raise ValueError("account_number is required for bank transaction rules")

        with self.conn.session as s:
            params = {
                'name': name,
                'priority': priority,
                'conditions': json.dumps(conditions),
                'category': category,
                'tag': tag,
                'service': service,
                'account_number': account_number,
                'is_active': 1 if is_active else 0,
                'created_date': datetime.now().isoformat()
            }

            query = sa.text(f"""
                INSERT INTO {self.table} ({self.name_col}, {self.priority_col}, {self.conditions_col}, 
                                         {self.category_col}, {self.tag_col}, {self.service_col}, 
                                         {self.account_number_col}, {self.is_active_col}, {self.created_date_col})
                VALUES (:name, :priority, :conditions, :category, :tag, :service, :account_number, :is_active, :created_date)
            """)
            result = s.execute(query, params)
            s.commit()
            return result.lastrowid

    def update_rule(self, rule_id: int, name: str = None, conditions: List[Dict[str, Any]] = None,
                    category: str = None, tag: str = None, priority: int = None,
                    is_active: bool = None) -> bool:
        """Update an existing rule. Only updates provided fields."""
        updates = []
        params = {'id': int(rule_id)}

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
            result = s.execute(query, params)
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

    def apply_rules_to_transactions(self, service: Literal['credit_card', 'bank']) -> int:
        """
        Apply all active rules to untagged transactions for the specified service.
        Returns the number of transactions that were tagged.

        This method uses a priority-based approach where higher priority rules are applied first.
        """
        with self.conn.session as s:
            rules = self._get_active_rules_for_service(s, service)
            total_tagged = 0

            for rule in rules:
                tagged_count = self._apply_single_rule(s, rule, service)
                total_tagged += tagged_count

            s.commit()
            return total_tagged

    def _get_active_rules_for_service(self, session: Session, service: Literal['credit_card', 'bank']) -> List[sa.Row]:
        """
        Get all active rules for the specified service, ordered by priority.

        Args:
            session: Database session
            service: Transaction service type

        Returns:
            List of rule records ordered by priority (highest first) then by ID
        """
        rules_query = f"""
            SELECT * FROM {self.table} 
            WHERE {self.service_col} = :service AND {self.is_active_col} = 1
            ORDER BY {self.priority_col} DESC, {self.id_col}
        """
        rules_result = session.execute(text(rules_query), {'service': service})
        return list(rules_result.fetchall())

    def _apply_single_rule(self, session: Session, rule: sa.Row, service: Literal['credit_card', 'bank']) -> int:
        """
        Apply a single rule to untagged transactions.

        Args:
            session: Database session
            rule: Rule record from database
            service: Transaction service type

        Returns:
            Number of transactions that were tagged by this rule
        """
        transaction_table = Tables.CREDIT_CARD.value if service == 'credit_card' else Tables.BANK.value

        where_conditions, params = self._build_rule_where_clause(rule, service)

        update_query = f"""
            UPDATE {transaction_table}
            SET {TransactionsTableFields.CATEGORY.value} = :category,
                {TransactionsTableFields.TAG.value} = :tag
            WHERE {' AND '.join(where_conditions)}
        """

        result = session.execute(text(update_query), params)
        return result.rowcount

    def _build_rule_where_clause(self, rule: sa.Row, service: Literal['credit_card', 'bank']) -> tuple[List[str], Dict[str, Any]]:
        """
        Build complete WHERE clause and parameters for a rule.

        Args:
            rule: Rule record from database
            service: Transaction service type

        Returns:
            Tuple of WHERE conditions list and parameters dictionary
        """
        # Access row data using _mapping to get column values by name
        rule_data = rule._mapping
        
        conditions = json.loads(rule_data[self.conditions_col])
        category = rule_data[self.category_col]
        tag = rule_data[self.tag_col]
        account_number = rule_data[self.account_number_col]

        where_conditions = [f"{TransactionsTableFields.CATEGORY.value} IS NULL"]
        params = {'category': category, 'tag': tag}

        # Add account number condition for bank transactions
        if service == 'bank' and account_number:
            where_conditions.append(f"{TransactionsTableFields.ACCOUNT_NUMBER.value} = :account_number")
            params['account_number'] = account_number

        # Add rule conditions
        for i, condition in enumerate(conditions):
            param_name = f'cond_{i}'
            self._build_condition_clause(condition, param_name, where_conditions, params)

        return where_conditions, params

    def _build_condition_clause(self, condition: Dict[str, Any], param_name: str,
                                where_conditions: List[str], params: Dict[str, Any]) -> None:
        """
        Build WHERE clause and parameters for a single rule condition.

        Args:
            condition: Rule condition with field, operator, and value
            param_name: Unique parameter name for this condition
            where_conditions: List to append WHERE clause to (modified in place)
            params: Dictionary to add parameters to (modified in place)
        """
        field = condition['field']
        operator = condition['operator']
        value = condition['value']

        db_field = self._map_field_to_db_column(field)
        if not db_field:
            return  # Skip unknown fields

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

    def _map_field_to_db_column(self, field: str) -> Optional[str]:
        """
        Map a rule condition field to its corresponding database column.

        Args:
            field: Field name from rule condition

        Returns:
            Database column name or None if field is unknown
        """
        field_mapping = {
            'description': TransactionsTableFields.DESCRIPTION.value,
            'amount': TransactionsTableFields.AMOUNT.value,
            'provider': TransactionsTableFields.PROVIDER.value,
            'account_name': TransactionsTableFields.ACCOUNT_NAME.value,
            'account_number': TransactionsTableFields.ACCOUNT_NUMBER.value,
        }
        return field_mapping.get(field)
