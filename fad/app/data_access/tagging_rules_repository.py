import json
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import (
    Tables,
    TaggingRulesTableFields,
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
