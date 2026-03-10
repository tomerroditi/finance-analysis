"""
Unit tests for BudgetRepository CRUD operations.
"""

import pytest
from sqlalchemy.orm import Session

from backend.repositories.budget_repository import BudgetRepository


class TestBudgetRepository:
    """Tests for BudgetRepository CRUD operations."""

    def test_add_monthly_rule(self, db_session: Session):
        """Verify adding a monthly budget rule persists correctly."""
        repo = BudgetRepository(db_session)
        repo.add(
            name="Food",
            amount=2000.0,
            category="Food",
            tags="Groceries;Restaurants",
            month=1,
            year=2024,
        )

        result = repo.read_all()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Food"
        assert row["amount"] == 2000.0
        assert row["category"] == "Food"
        assert row["tags"] == "Groceries;Restaurants"
        assert row["month"] == 1
        assert row["year"] == 2024

    def test_add_project_rule(self, db_session: Session):
        """Verify adding a project rule (month=None, year=None) persists correctly."""
        repo = BudgetRepository(db_session)
        repo.add(
            name="Wedding Budget",
            amount=50000.0,
            category="Wedding",
            tags="Venue;Catering",
            month=None,
            year=None,
        )

        result = repo.read_all()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Wedding Budget"
        assert row["amount"] == 50000.0
        assert row["category"] == "Wedding"
        assert row["tags"] == "Venue;Catering"
        assert row["month"] is None
        assert row["year"] is None

    def test_read_all(self, db_session: Session):
        """Verify read_all returns all rules as DataFrame."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Transport", 500.0, "Transport", "Gas", month=1, year=2024)
        repo.add("Wedding", 50000.0, "Wedding", "Venue;Catering", month=None, year=None)

        result = repo.read_all()
        assert len(result) == 3
        assert set(result["name"].tolist()) == {"Food", "Transport", "Wedding"}

    def test_read_by_id(self, db_session: Session):
        """Verify read_by_id returns correct rule."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Transport", 500.0, "Transport", "Gas", month=1, year=2024)

        all_rules = repo.read_all()
        target_id = int(all_rules.iloc[0]["id"])

        result = repo.read_by_id(target_id)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Food"

    def test_read_by_id_not_found(self, db_session: Session):
        """Verify read_by_id returns empty DataFrame for nonexistent ID."""
        repo = BudgetRepository(db_session)
        result = repo.read_by_id(999)
        assert result.empty

    def test_read_by_month(self, db_session: Session):
        """Verify read_by_month filters correctly."""
        repo = BudgetRepository(db_session)
        repo.add("Food Jan", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Food Feb", 2500.0, "Food", "Groceries", month=2, year=2024)
        repo.add("Transport Jan", 500.0, "Transport", "Gas", month=1, year=2024)

        result = repo.read_by_month(year=2024, month=1)
        assert len(result) == 2
        assert set(result["name"].tolist()) == {"Food Jan", "Transport Jan"}

    def test_read_by_month_excludes_project_rules(self, db_session: Session):
        """Verify read_by_month does not return project rules (null month/year)."""
        repo = BudgetRepository(db_session)
        repo.add("Food Jan", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Wedding", 50000.0, "Wedding", "Venue", month=None, year=None)

        result = repo.read_by_month(year=2024, month=1)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Food Jan"

    def test_read_project_rules(self, db_session: Session):
        """Verify read_project_rules returns only rules with null month/year."""
        repo = BudgetRepository(db_session)
        repo.add("Food Jan", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Wedding", 50000.0, "Wedding", "Venue;Catering", month=None, year=None)
        repo.add("Renovation", 25000.0, "Renovation", "Materials;Labor", month=None, year=None)

        result = repo.read_project_rules()
        assert len(result) == 2
        assert set(result["name"].tolist()) == {"Wedding", "Renovation"}

    def test_update_rule(self, db_session: Session):
        """Verify update changes the specified fields."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        repo.update(rule_id, amount=3000.0, name="Food Updated")

        updated = repo.read_by_id(rule_id)
        assert updated.iloc[0]["amount"] == 3000.0
        assert updated.iloc[0]["name"] == "Food Updated"
        # Unchanged fields remain the same
        assert updated.iloc[0]["category"] == "Food"

    def test_update_nonexistent_rule_raises(self, db_session: Session):
        """Verify update raises ValueError for nonexistent rule ID."""
        repo = BudgetRepository(db_session)
        with pytest.raises(ValueError, match="No rule found with ID 999"):
            repo.update(999, amount=5000.0)

    def test_delete_rule(self, db_session: Session):
        """Verify delete removes the rule."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        repo.delete(rule_id)

        result = repo.read_all()
        assert result.empty

    def test_delete_by_month(self, db_session: Session):
        """Verify delete_by_month removes all rules for that month."""
        repo = BudgetRepository(db_session)
        repo.add("Food Jan", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Transport Jan", 500.0, "Transport", "Gas", month=1, year=2024)
        repo.add("Food Feb", 2500.0, "Food", "Groceries", month=2, year=2024)

        repo.delete_by_month(year=2024, month=1)

        result = repo.read_all()
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Food Feb"

    def test_delete_by_category(self, db_session: Session):
        """Verify delete_by_category removes only project rules for that category."""
        repo = BudgetRepository(db_session)
        # Project rule
        repo.add("Wedding Budget", 50000.0, "Wedding", "Venue;Catering", month=None, year=None)
        # Monthly rule with same category -- should NOT be deleted
        repo.add("Wedding Jan", 5000.0, "Wedding", "Venue", month=1, year=2024)
        # Another project rule
        repo.add("Renovation", 25000.0, "Renovation", "Materials", month=None, year=None)

        repo.delete_by_category("Wedding")

        result = repo.read_all()
        assert len(result) == 2
        names = set(result["name"].tolist())
        assert "Wedding Budget" not in names
        assert "Wedding Jan" in names
        assert "Renovation" in names

    def test_delete_by_category_and_tags(self, db_session: Session):
        """Verify delete_by_category_and_tags removes only matching project rules."""
        repo = BudgetRepository(db_session)
        repo.add("Wedding Venue", 30000.0, "Wedding", "Venue", month=None, year=None)
        repo.add("Wedding Catering", 20000.0, "Wedding", "Catering", month=None, year=None)
        # Monthly rule -- should NOT be deleted
        repo.add("Wedding Jan", 5000.0, "Wedding", "Venue", month=1, year=2024)

        repo.delete_by_category_and_tags("Wedding", "Venue")

        result = repo.read_all()
        assert len(result) == 2
        names = set(result["name"].tolist())
        assert "Wedding Venue" not in names
        assert "Wedding Catering" in names
        assert "Wedding Jan" in names

    def test_tags_stored_as_semicolon_string(self, db_session: Session):
        """Verify tags are stored as semicolon-separated string."""
        repo = BudgetRepository(db_session)
        tags = "Groceries;Restaurants;Coffee"
        repo.add("Food", 2000.0, "Food", tags, month=1, year=2024)

        result = repo.read_all()
        stored_tags = result.iloc[0]["tags"]
        assert stored_tags == tags
        assert len(stored_tags.split(";")) == 3


class TestBudgetRepositoryEmptyUpdate:
    """Tests for update with empty fields."""

    def test_update_empty_fields_returns_early(self, db_session: Session):
        """Verify update returns immediately when no fields are provided."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        # Should return without raising or executing a query
        repo.update(rule_id)

        # Verify no changes were made
        result = repo.read_by_id(rule_id)
        assert result.iloc[0]["amount"] == 2000.0
        assert result.iloc[0]["name"] == "Food"
