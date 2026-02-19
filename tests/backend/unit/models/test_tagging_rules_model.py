"""
Unit tests for TaggingRule ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.tagging_rules import TaggingRule


class TestTaggingRule:
    """Tests for TaggingRule model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert TaggingRule.__tablename__ == Tables.TAGGING_RULES.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        rule = TaggingRule(
            name="Grocery Stores",
            conditions={
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "supermarket",
            },
            category="Food",
            tag="Groceries",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.name == "Grocery Stores"
        assert rule.category == "Food"
        assert rule.tag == "Groceries"

    def test_conditions_stored_as_json(self, db_session: Session):
        """Test that conditions are stored and retrieved as JSON."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "equals",
                    "value": "test",
                },
                {
                    "type": "CONDITION",
                    "field": "amount",
                    "operator": "lt",
                    "value": -10,
                },
            ],
        }
        rule = TaggingRule(
            name="JSON Rule",
            conditions=conditions,
            category="Other",
            tag="Misc",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.conditions["type"] == "AND"
        assert len(rule.conditions["subconditions"]) == 2

    def test_nullable_constraints(self, db_session: Session):
        """Test that name, conditions, category, and tag are required."""
        rule = TaggingRule(
            name="Required Fields",
            conditions={
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "x",
            },
            category="Test",
            tag="Test",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.name is not None
        assert rule.conditions is not None
        assert rule.category is not None
        assert rule.tag is not None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        rule = TaggingRule(
            name="Timestamp Test",
            conditions={
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "x",
            },
            category="Test",
            tag="Test",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert hasattr(rule, "created_at")
        assert rule.created_at is not None
