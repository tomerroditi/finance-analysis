"""
Tagging rules repository with SQLAlchemy ORM.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.models.tagging import TaggingRule


class TaggingRulesRepository:
    """
    Repository for CRUD operations on tagging rules using ORM.
    """

    def __init__(self, db: Session):
        self.db = db

    def _assure_table_exists(self) -> None:
        pass

    def get_all_rules(self, active_only: bool = True) -> pd.DataFrame:
        """Get all tagging rules, optionally filtered by active status."""
        stmt = select(TaggingRule)
        if active_only:
            stmt = stmt.where(TaggingRule.is_active == 1)

        stmt = stmt.order_by(TaggingRule.priority.desc(), TaggingRule.id)
        return pd.read_sql(stmt, self.db.bind)

    def get_rule_by_id(self, rule_id: int) -> Optional[pd.Series]:
        """Get a specific rule by ID."""
        stmt = select(TaggingRule).where(TaggingRule.id == rule_id)
        df = pd.read_sql(stmt, self.db.bind)
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
        is_active: bool = True,
    ) -> int:
        """Add a new tagging rule. Returns the new rule ID."""
        new_rule = TaggingRule(
            name=name,
            conditions=json.dumps(conditions, ensure_ascii=False),
            category=category,
            tag=tag,
            priority=priority,
            is_active=1 if is_active else 0,
            created_date=datetime.now().isoformat(),
        )
        self.db.add(new_rule)
        self.db.commit()
        return new_rule.id

    def update_rule(
        self,
        rule_id: int,
        name: str = None,
        conditions: List[Dict[str, Any]] = None,
        category: str = None,
        tag: str = None,
        priority: int = None,
        is_active: bool = None,
    ) -> bool:
        """Update an existing rule. Only updates provided fields."""
        updates = {}
        if name is not None:
            updates["name"] = name
        if conditions is not None:
            updates["conditions"] = json.dumps(conditions)
        if category is not None:
            updates["category"] = category
        if tag is not None:
            updates["tag"] = tag
        if priority is not None:
            updates["priority"] = priority
        if is_active is not None:
            updates["is_active"] = 1 if is_active else 0

        if not updates:
            return False

        stmt = (
            update(TaggingRule).where(TaggingRule.id == int(rule_id)).values(**updates)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID."""
        stmt = delete(TaggingRule).where(TaggingRule.id == int(rule_id))
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount > 0

    def delete_rules_by_category_and_tag(self, category: str, tag: str) -> int:
        """Delete all rules with the specified category and tag."""
        stmt = delete(TaggingRule).where(
            TaggingRule.category == category, TaggingRule.tag == tag
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def update_category_for_tag(
        self, old_category: str, new_category: str, tag: str
    ) -> int:
        """Update category for all rules with the specified old_category and tag."""
        stmt = (
            update(TaggingRule)
            .where(TaggingRule.category == old_category)
            .where(TaggingRule.tag == tag)
            .values(category=new_category)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def delete_rules_by_category(self, category: str) -> int:
        """Delete all rules with the specified category."""
        stmt = delete(TaggingRule).where(TaggingRule.category == category)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount
