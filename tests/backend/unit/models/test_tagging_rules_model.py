"""
Unit tests for TaggingRule ORM model.
"""

import pytest
from sqlalchemy import null
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.tagging_rules import TaggingRule


def _valid_fields() -> dict:
    """Return a complete, valid set of TaggingRule column values."""
    return {
        "name": "Grocery Stores",
        "conditions": {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "supermarket",
        },
        "category": "Food",
        "tag": "Groceries",
    }


class TestTaggingRule:
    """Tests for TaggingRule model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert TaggingRule.__tablename__ == Tables.TAGGING_RULES.value

    def test_conditions_stored_as_json(self, db_session: Session):
        """A nested condition tree round-trips through the JSON column."""
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
        rule = TaggingRule(**{**_valid_fields(), "conditions": conditions})
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.conditions == conditions
        assert rule.created_at is not None

    @pytest.mark.parametrize("column", ["name", "conditions", "category", "tag"])
    def test_required_column_rejects_null(self, db_session: Session, column):
        """Each NOT NULL column actually raises IntegrityError when nulled.

        The previous version of this test inserted a fully valid row and then
        asserted the fields were not None, which can never fail and proved
        nothing about the constraints.

        The null is written as SQLAlchemy's ``null()`` rather than Python
        ``None`` because ``conditions`` is a ``JSON`` column: with the default
        ``none_as_null=False`` a Python ``None`` is serialised to the JSON
        document ``null``, which satisfies NOT NULL.
        """
        db_session.add(TaggingRule(**{**_valid_fields(), column: null()}))

        with pytest.raises(IntegrityError):
            db_session.commit()
