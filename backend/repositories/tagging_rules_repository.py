"""
Tagging rules repository with pure SQLAlchemy (no Streamlit dependencies).

This module provides data access for automated tagging rule operations.
"""
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from fad.app.naming_conventions import Tables, TaggingRulesTableFields


class TaggingRulesRepository:
    """
    Repository for CRUD operations on tagging rules.
    
    Manages automated rules for categorizing and tagging transactions.
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

    def __init__(self, db: Session):
        """
        Initialize the tagging rules repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._assure_table_exists()

    def _assure_table_exists(self) -> None:
        """Create the tagging rules table if it doesn't exist."""
        self.db.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    {self.id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                    {self.name_col} TEXT NOT NULL,
                    {self.priority_col} INTEGER DEFAULT 1,
                    {self.conditions_col} TEXT NOT NULL,
                    {self.category_col} TEXT NOT NULL,
                    {self.tag_col} TEXT NOT NULL,
                    {self.is_active_col} INTEGER DEFAULT 1,
                    {self.created_date_col} TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        self.db.commit()

    def get_all_rules(self, active_only: bool = True) -> pd.DataFrame:
        """Get all tagging rules, optionally filtered by active status."""
        if active_only:
            query = f"""
                SELECT * FROM {self.table}
                WHERE {self.is_active_col} = 1
                ORDER BY {self.priority_col} DESC, {self.id_col}
            """
        else:
            query = f"""
                SELECT * FROM {self.table}
                ORDER BY {self.priority_col} DESC, {self.id_col}
            """
        
        result = self.db.execute(text(query))
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def get_rule_by_id(self, rule_id: int) -> Optional[pd.Series]:
        """Get a specific rule by ID."""
        result = self.db.execute(
            text(f'SELECT * FROM {self.table} WHERE {self.id_col} = :id'),
            {'id': int(rule_id)}
        )
        columns = result.keys()
        data = result.fetchall()
        df = pd.DataFrame(data, columns=columns)
        
        if not df.empty:
            return df.iloc[0]
        return None

    def add_rule(
        self, 
        name: str, 
        conditions: List[Dict[str, Any]], 
        category: str, 
        tag: str, 
        priority: int = 1, 
        is_active: bool = True
    ) -> int:
        """Add a new tagging rule. Returns the new rule ID."""
        result = self.db.execute(
            text(f"""
                INSERT INTO {self.table} (
                    {self.name_col}, {self.priority_col}, {self.conditions_col},
                    {self.category_col}, {self.tag_col}, {self.is_active_col}, {self.created_date_col}
                )
                VALUES (:name, :priority, :conditions, :category, :tag, :is_active, :created_date)
            """),
            {
                'name': name,
                'priority': priority,
                'conditions': json.dumps(conditions, ensure_ascii=False),
                'category': category,
                'tag': tag,
                'is_active': 1 if is_active else 0,
                'created_date': datetime.now().isoformat()
            }
        )
        self.db.commit()
        return result.lastrowid

    def update_rule(
        self, 
        rule_id: int, 
        name: str = None, 
        conditions: List[Dict[str, Any]] = None, 
        category: str = None, 
        tag: str = None, 
        priority: int = None, 
        is_active: bool = None
    ) -> bool:
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

        params['id'] = int(rule_id)
        result = self.db.execute(
            text(f"UPDATE {self.table} SET {', '.join(updates)} WHERE {self.id_col} = :id"),
            params
        )
        self.db.commit()
        return result.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        result = self.db.execute(
            text(f"DELETE FROM {self.table} WHERE {self.id_col} = :id"),
            {'id': int(rule_id)}
        )
        self.db.commit()
        return result.rowcount > 0

    def delete_rules_by_category_and_tag(self, category: str, tag: str) -> int:
        """Delete all rules with the specified category and tag."""
        result = self.db.execute(
            text(f"""
                DELETE FROM {self.table}
                WHERE {self.category_col} = :category AND {self.tag_col} = :tag
            """),
            {'category': category, 'tag': tag}
        )
        self.db.commit()
        return result.rowcount

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> int:
        """Update category for all rules with the specified old_category and tag."""
        result = self.db.execute(
            text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :new_category
                WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
            """),
            {'new_category': new_category, 'old_category': old_category, 'tag': tag}
        )
        self.db.commit()
        return result.rowcount

    def delete_rules_by_category(self, category: str) -> int:
        """Delete all rules with the specified category."""
        result = self.db.execute(
            text(f"DELETE FROM {self.table} WHERE {self.category_col} = :category"),
            {'category': category}
        )
        self.db.commit()
        return result.rowcount
