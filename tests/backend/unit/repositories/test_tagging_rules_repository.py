"""
Unit tests for TaggingRulesRepository CRUD operations.
"""

from sqlalchemy.orm import Session

from backend.repositories.tagging_rules_repository import TaggingRulesRepository


def _make_conditions(field: str, operator: str, value: str) -> dict:
    """Build a simple AND-wrapped condition dict for testing."""
    return {
        "type": "AND",
        "subconditions": [
            {
                "type": "CONDITION",
                "field": field,
                "operator": operator,
                "value": value,
            }
        ],
    }


class TestTaggingRulesRepository:
    """Tests for TaggingRulesRepository operations."""

    def test_add_rule(self, db_session: Session):
        """Verify adding a tagging rule returns its ID."""
        repo = TaggingRulesRepository(db_session)
        conditions = _make_conditions("description", "contains", "SUPERMARKET")

        rule_id = repo.add_rule(
            name="Supermarket Rule",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )

        assert isinstance(rule_id, int)
        assert rule_id > 0

    def test_get_all_rules_empty(self, db_session: Session):
        """Verify get_all_rules returns empty DataFrame when no rules exist."""
        repo = TaggingRulesRepository(db_session)

        result = repo.get_all_rules()

        assert result.empty
        expected_columns = [
            "id", "name", "conditions", "category", "tag",
            "created_at", "updated_at",
        ]
        assert list(result.columns) == expected_columns

    def test_get_all_rules(self, db_session: Session):
        """Verify get_all_rules returns all rules with conditions."""
        repo = TaggingRulesRepository(db_session)
        repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )
        repo.add_rule(
            name="Uber Rule",
            conditions=_make_conditions("description", "contains", "UBER"),
            category="Transport",
            tag="Rides",
        )
        repo.add_rule(
            name="Netflix Rule",
            conditions=_make_conditions("description", "contains", "Netflix"),
            category="Entertainment",
            tag="Streaming",
        )

        result = repo.get_all_rules()

        assert len(result) == 3
        assert set(result["name"].tolist()) == {
            "Supermarket Rule", "Uber Rule", "Netflix Rule",
        }
        assert set(result["category"].tolist()) == {
            "Food", "Transport", "Entertainment",
        }
        # Verify conditions are stored as dicts (deserialized JSON)
        for _, row in result.iterrows():
            assert isinstance(row["conditions"], dict)
            assert "type" in row["conditions"]
            assert "subconditions" in row["conditions"]

    def test_get_rule_by_id(self, db_session: Session):
        """Verify retrieving a single rule by ID."""
        repo = TaggingRulesRepository(db_session)
        conditions = _make_conditions("description", "contains", "SUPERMARKET")
        rule_id = repo.add_rule(
            name="Supermarket Rule",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )

        rule = repo.get_rule_by_id(rule_id)

        assert rule is not None
        assert rule.id == rule_id
        assert rule.name == "Supermarket Rule"
        assert rule.category == "Food"
        assert rule.tag == "Groceries"
        assert rule.conditions == conditions

    def test_get_rule_by_id_not_found(self, db_session: Session):
        """Verify None returned for non-existent ID."""
        repo = TaggingRulesRepository(db_session)

        result = repo.get_rule_by_id(999)

        assert result is None

    def test_update_rule(self, db_session: Session):
        """Verify updating rule fields."""
        repo = TaggingRulesRepository(db_session)
        rule_id = repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )

        new_conditions = _make_conditions("description", "contains", "GROCERY")
        success = repo.update_rule(
            rule_id,
            name="Grocery Rule",
            category="Food",
            tag="Groceries Updated",
            conditions=new_conditions,
        )

        assert success is True
        updated = repo.get_rule_by_id(rule_id)
        assert updated.name == "Grocery Rule"
        assert updated.tag == "Groceries Updated"
        assert updated.conditions == new_conditions

    def test_update_rule_not_found(self, db_session: Session):
        """Verify update returns False for non-existent rule."""
        repo = TaggingRulesRepository(db_session)

        result = repo.update_rule(999, name="Does Not Exist")

        assert result is False

    def test_delete_rule(self, db_session: Session):
        """Verify deleting a rule by ID."""
        repo = TaggingRulesRepository(db_session)
        rule_id = repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )

        success = repo.delete_rule(rule_id)

        assert success is True
        assert repo.get_rule_by_id(rule_id) is None
        assert repo.get_all_rules().empty

    def test_delete_rule_not_found(self, db_session: Session):
        """Verify delete returns False for non-existent rule."""
        repo = TaggingRulesRepository(db_session)

        result = repo.delete_rule(999)

        assert result is False

    def test_delete_rules_by_category(self, db_session: Session):
        """Verify deleting all rules for a category."""
        repo = TaggingRulesRepository(db_session)
        repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )
        repo.add_rule(
            name="Restaurant Rule",
            conditions=_make_conditions("description", "contains", "RESTAURANT"),
            category="Food",
            tag="Restaurants",
        )
        repo.add_rule(
            name="Uber Rule",
            conditions=_make_conditions("description", "contains", "UBER"),
            category="Transport",
            tag="Rides",
        )

        success = repo.delete_rules_by_category("Food")

        assert success is True
        remaining = repo.get_all_rules()
        assert len(remaining) == 1
        assert remaining.iloc[0]["name"] == "Uber Rule"

    def test_delete_rules_by_category_not_found(self, db_session: Session):
        """Verify delete_rules_by_category returns False when no rules match."""
        repo = TaggingRulesRepository(db_session)

        result = repo.delete_rules_by_category("NonExistent")

        assert result is False

    def test_delete_rules_by_category_and_tag(self, db_session: Session):
        """Verify deleting rules matching both category and tag."""
        repo = TaggingRulesRepository(db_session)
        repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )
        repo.add_rule(
            name="Restaurant Rule",
            conditions=_make_conditions("description", "contains", "RESTAURANT"),
            category="Food",
            tag="Restaurants",
        )
        repo.add_rule(
            name="Uber Rule",
            conditions=_make_conditions("description", "contains", "UBER"),
            category="Transport",
            tag="Rides",
        )

        success = repo.delete_rules_by_category_and_tag("Food", "Groceries")

        assert success is True
        remaining = repo.get_all_rules()
        assert len(remaining) == 2
        remaining_names = set(remaining["name"].tolist())
        assert "Supermarket Rule" not in remaining_names
        assert "Restaurant Rule" in remaining_names
        assert "Uber Rule" in remaining_names

    def test_delete_rules_by_category_and_tag_not_found(self, db_session: Session):
        """Verify delete_rules_by_category_and_tag returns False when no match."""
        repo = TaggingRulesRepository(db_session)
        repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )

        result = repo.delete_rules_by_category_and_tag("Food", "NonExistent")

        assert result is False

    def test_update_category_for_tag(self, db_session: Session):
        """Verify updating category for rules matching a tag."""
        repo = TaggingRulesRepository(db_session)
        repo.add_rule(
            name="Supermarket Rule",
            conditions=_make_conditions("description", "contains", "SUPERMARKET"),
            category="Food",
            tag="Groceries",
        )
        repo.add_rule(
            name="Farmers Market",
            conditions=_make_conditions("description", "contains", "FARMERS"),
            category="Food",
            tag="Groceries",
        )
        repo.add_rule(
            name="Restaurant Rule",
            conditions=_make_conditions("description", "contains", "RESTAURANT"),
            category="Food",
            tag="Restaurants",
        )

        success = repo.update_category_for_tag("Food", "Essentials", "Groceries")

        assert success is True
        all_rules = repo.get_all_rules()
        groceries_rules = all_rules[all_rules["tag"] == "Groceries"]
        assert len(groceries_rules) == 2
        for _, row in groceries_rules.iterrows():
            assert row["category"] == "Essentials"
        # The Restaurants rule should be unchanged
        restaurants_rule = all_rules[all_rules["tag"] == "Restaurants"]
        assert len(restaurants_rule) == 1
        assert restaurants_rule.iloc[0]["category"] == "Food"

    def test_update_category_for_tag_not_found(self, db_session: Session):
        """Verify update_category_for_tag returns False when no match."""
        repo = TaggingRulesRepository(db_session)

        result = repo.update_category_for_tag("NonExistent", "NewCategory", "NoTag")

        assert result is False
