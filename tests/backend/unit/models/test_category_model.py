"""Unit tests for the Category ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.category import Category


class TestCategoryModel:
    """Tests for Category model constraints and defaults."""

    def test_create_category_with_tags(self, db_session):
        """Verify category created with name, tags list, and icon."""
        cat = Category(name="Food", tags=["Groceries", "Restaurants"], icon="🍔")
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)

        assert cat.id is not None
        assert cat.name == "Food"
        assert cat.tags == ["Groceries", "Restaurants"]
        assert cat.icon == "🍔"
        assert cat.created_at is not None

    def test_create_category_defaults(self, db_session):
        """Verify default empty tags list and null icon."""
        cat = Category(name="Salary")
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)

        assert cat.tags == []
        assert cat.icon is None

    def test_unique_name_constraint(self, db_session):
        """Verify duplicate category name raises IntegrityError."""
        db_session.add(Category(name="Food", tags=[]))
        db_session.commit()

        db_session.add(Category(name="Food", tags=["Other"]))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_name_not_nullable(self, db_session):
        """Verify null name raises IntegrityError."""
        db_session.add(Category(name=None, tags=[]))
        with pytest.raises(IntegrityError):
            db_session.commit()
