import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.tagging_rules import TaggingRule


class TaggingRulesRepository:
    """
    Repository for managing tagging rules in the database.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_all_rules(self) -> pd.DataFrame:
        """
        Get all tagging rules from the database.
        """
        query = select(TaggingRule)

        rules = self.db.execute(query).scalars().all()

        # Convert to DataFrame for consistency with other services
        data = [
            {
                "id": r.id,
                "name": r.name,
                "conditions": r.conditions,
                "category": r.category,
                "tag": r.tag,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rules
        ]

        if not data:
            return pd.DataFrame(
                columns=[
                    "id",
                    "name",
                    "conditions",
                    "category",
                    "tag",
                    "created_at",
                    "updated_at",
                ]
            )

        return pd.DataFrame(data)

    def get_rule_by_id(self, rule_id: int) -> TaggingRule | None:
        """
        Get a specific rule by ID.
        """
        return self.db.get(TaggingRule, rule_id)

    def add_rule(
        self,
        name: str,
        conditions: dict,
        category: str,
        tag: str,
    ) -> int:
        """
        Add a new tagging rule.
        """
        new_rule = TaggingRule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
        )
        self.db.add(new_rule)
        self.db.commit()
        self.db.refresh(new_rule)
        return new_rule.id

    def update_rule(self, rule_id: int, **kwargs) -> bool:
        """
        Update an existing rule.
        """
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return False

        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        self.db.commit()
        self.db.refresh(rule)
        return True

    def delete_rule(self, rule_id: int) -> bool:
        """
        Delete a rule by ID.
        """
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return False

        self.db.delete(rule)
        self.db.commit()
        return True
