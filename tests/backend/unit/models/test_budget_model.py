"""
Unit tests for BudgetRule ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.budget import BudgetRule


class TestBudgetRule:
    """Tests for BudgetRule model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert BudgetRule.__tablename__ == Tables.BUDGET_RULES.value

    def test_monthly_budget_rule(self, db_session: Session):
        """Test creating a monthly budget rule."""
        rule = BudgetRule(
            name="Total Budget",
            amount=5000.0,
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.name == "Total Budget"
        assert rule.amount == 5000.0
        assert rule.year == 2026
        assert rule.month == 1

    def test_category_budget_rule(self, db_session: Session):
        """Test creating a category budget rule."""
        rule = BudgetRule(
            name="Monthly Food",
            amount=1500.0,
            category="Food",
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.category == "Food"
        assert rule.tags is None

    def test_tag_budget_rule(self, db_session: Session):
        """Test creating a budget rule with tags."""
        rule = BudgetRule(
            name="Restaurant Budget",
            amount=500.0,
            category="Food",
            tags="Restaurants",
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.tags == "Restaurants"

    def test_project_budget_rule(self, db_session: Session):
        """Test creating a project budget (no year/month)."""
        rule = BudgetRule(
            name="Home Renovation",
            amount=50000.0,
            category="Home",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.year is None
        assert rule.month is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        rule = BudgetRule(name="Test", amount=100.0)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert hasattr(rule, "created_at")
        assert rule.created_at is not None
