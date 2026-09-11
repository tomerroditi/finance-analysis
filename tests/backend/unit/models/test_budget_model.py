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

    def test_round_trip_all_columns(self, db_session: Session):
        """Every column round-trips, and the nullable ones default to ``None``.

        A monthly tag rule exercises the fully-populated shape; a bare project
        rule (no year/month/tags/period_type) exercises the nullable defaults.
        """
        monthly = BudgetRule(
            name="Restaurant Budget",
            amount=500.0,
            category="Food",
            tags="Restaurants;Coffee",
            year=2026,
            month=1,
            period_type="monthly",
        )
        project = BudgetRule(name="Home Renovation", amount=50000.0, category="Home")
        db_session.add_all([monthly, project])
        db_session.commit()
        for rule in (monthly, project):
            db_session.refresh(rule)

        assert monthly.id is not None and project.id is not None
        assert monthly.id != project.id
        assert (monthly.name, monthly.amount, monthly.category) == (
            "Restaurant Budget", 500.0, "Food",
        )
        assert monthly.tags == "Restaurants;Coffee"
        assert (monthly.year, monthly.month, monthly.period_type) == (2026, 1, "monthly")

        assert (project.name, project.amount, project.category) == (
            "Home Renovation", 50000.0, "Home",
        )
        assert project.tags is None
        assert project.year is None
        assert project.month is None
        assert project.period_type is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        rule = BudgetRule(name="Test", amount=100.0)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert hasattr(rule, "created_at")
        assert rule.created_at is not None


class TestBudgetRulePeriodType:
    """The period_type discriminator column on BudgetRule."""

    def test_period_type_column_exists_and_persists(self, db_session):
        """A BudgetRule stores and returns its period_type value."""
        from backend.models.budget import BudgetRule

        rule = BudgetRule(
            name="Vacations", amount=20000.0, category="Travel",
            tags="Hotels;Activities", year=2026, month=None,
            period_type="yearly",
        )
        db_session.add(rule)
        db_session.commit()

        fetched = db_session.query(BudgetRule).filter_by(name="Vacations").one()
        assert fetched.period_type == "yearly"
        assert fetched.month is None
        assert fetched.year == 2026
