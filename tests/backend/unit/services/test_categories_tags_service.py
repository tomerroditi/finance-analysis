"""
Tests for CategoriesTagsService.

Covers reading categories/tags/icons, adding/deleting categories,
and adding/deleting/reallocating tags.
"""

import pytest

import backend.services.tagging_service as ts
from backend.constants.categories import PROTECTED_CATEGORIES
from backend.services.tagging_service import CategoriesTagsService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_categories_cache():
    """Reset categories cache before each test."""
    ts._categories_cache = None
    yield
    ts._categories_cache = None


@pytest.fixture
def categories_service(db_session, seed_categories):
    """Create CategoriesTagsService backed by seeded DB categories."""
    return CategoriesTagsService(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceRead:
    """Tests for reading categories, tags, and icons."""

    def test_get_categories_and_tags(self, categories_service, sample_categories_yaml):
        """Verify categories are loaded from the database."""
        result = categories_service.get_categories_and_tags()

        assert isinstance(result, dict)
        assert "Food" in result
        assert "Groceries" in result["Food"]
        assert "Transport" in result
        assert result == sample_categories_yaml

    def test_get_categories_and_tags_copy(self, categories_service):
        """Verify copy=True returns a deep copy that does not affect the original."""
        copy = categories_service.get_categories_and_tags(copy=True)
        # Mutate the copy
        copy["Food"].append("Fast Food")
        copy["NewCategory"] = ["Tag1"]

        # Original cache should be unaffected
        original = categories_service.get_categories_and_tags()
        assert "Fast Food" not in original["Food"]
        assert "NewCategory" not in original

    def test_get_categories_icons(self, db_session, seed_categories):
        """Verify icons are loaded via TaggingRepository.get_categories_icons."""
        from backend.models.category import Category
        from sqlalchemy import select

        # Set an icon on Food category
        food = db_session.execute(
            select(Category).where(Category.name == "Food")
        ).scalar_one()
        food.icon = "fork-and-knife"
        db_session.commit()

        ts._categories_cache = None
        service = CategoriesTagsService(db_session)
        icons = service.get_categories_icons()

        assert icons["Food"] == "fork-and-knife"


# ---------------------------------------------------------------------------
# Class 2: Category management
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceCategories:
    """Tests for adding and deleting categories."""

    def test_add_category(self, categories_service):
        """Verify a new category is added successfully."""
        result = categories_service.add_category("Utilities", ["Electric", "Water"])

        assert result is True
        assert "Utilities" in categories_service.categories_and_tags
        assert categories_service.categories_and_tags["Utilities"] == [
            "Electric",
            "Water",
        ]

    def test_add_category_duplicate_rejected(self, categories_service):
        """Verify adding a category that already exists returns False."""
        # "Food" already exists in seed_categories
        result = categories_service.add_category("Food", ["New Tag"])

        assert result is False

    def test_add_category_empty_name_rejected(self, categories_service):
        """Verify adding a category with an empty or whitespace-only name returns False."""
        assert categories_service.add_category("", []) is False
        assert categories_service.add_category("   ", []) is False
        assert categories_service.add_category(None, []) is False

    def test_add_category_title_case(self, categories_service):
        """Verify category name is normalized to title case."""
        result = categories_service.add_category("health care", ["Doctor"])

        assert result is True
        assert "Health Care" in categories_service.categories_and_tags
        # Original casing should not appear
        assert "health care" not in categories_service.categories_and_tags

    def test_delete_category(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify deleting a category removes it and nullifies related transactions."""
        # "Food" category has transactions in seed_base_transactions
        assert "Food" in categories_service.categories_and_tags

        result = categories_service.delete_category("Food")

        assert result is True
        assert "Food" not in categories_service.categories_and_tags

    def test_delete_category_protected(self, categories_service):
        """Verify protected categories cannot be deleted."""
        for protected in PROTECTED_CATEGORIES:
            result = categories_service.delete_category(protected)
            assert result is False, f"Protected category '{protected}' should not be deletable"


# ---------------------------------------------------------------------------
# Class 3: Tag management
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceTags:
    """Tests for adding, deleting, and reallocating tags."""

    def test_add_tag(self, categories_service):
        """Verify adding a new tag to an existing category."""
        result = categories_service.add_tag("Food", "Bakery")

        assert result is True
        assert "Bakery" in categories_service.categories_and_tags["Food"]

    def test_add_tag_duplicate_rejected(self, categories_service):
        """Verify adding a duplicate tag to a category returns False."""
        # "Groceries" already exists under "Food"
        result = categories_service.add_tag("Food", "Groceries")

        assert result is False

    def test_delete_tag(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify deleting a tag removes it from the category and nullifies transactions."""
        assert "Groceries" in categories_service.categories_and_tags["Food"]

        result = categories_service.delete_tag("Food", "Groceries")

        assert result is True
        assert "Groceries" not in categories_service.categories_and_tags["Food"]

    def test_reallocate_tag(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify moving a tag between categories updates the in-memory dict."""
        assert "Groceries" in categories_service.categories_and_tags["Food"]
        assert "Groceries" not in categories_service.categories_and_tags["Home"]

        result = categories_service.reallocate_tag("Food", "Home", "Groceries")

        assert result is True
        assert "Groceries" not in categories_service.categories_and_tags["Food"]
        assert "Groceries" in categories_service.categories_and_tags["Home"]

    def test_reallocate_tag_invalid_category(self, categories_service):
        """Verify reallocating a tag to a non-existent category returns False."""
        result = categories_service.reallocate_tag(
            "Food", "NonExistent", "Groceries"
        )

        assert result is False
        # Tag should remain in the original category
        assert "Groceries" in categories_service.categories_and_tags["Food"]

    def test_add_new_credit_card_tags(self, categories_service, db_session):
        """Verify CC account tags are added to the Credit Cards category."""
        from backend.models.category import Category
        from backend.models.transaction import CreditCardTransaction

        # Add "Credit Cards" category to DB
        db_session.add(Category(name="Credit Cards", tags=[]))
        db_session.commit()
        categories_service._invalidate_cache()

        # Insert a credit card transaction so get_unique_accounts_tags returns data
        cc_tx = CreditCardTransaction(
            id="cc_test_1",
            date="2024-01-01",
            provider="isracard",
            account_name="Main Card",
            account_number="12345678",
            description="Test",
            amount=-50.0,
            source="credit_card_transactions",
        )
        db_session.add(cc_tx)
        db_session.commit()

        result = categories_service.add_new_credit_card_tags()

        assert result is True
        cc_tags = categories_service.categories_and_tags["Credit Cards"]
        # Should contain the tag derived from the CC transaction
        assert len(cc_tags) > 0
        # The tag format is "provider - account_name - last4digits"
        # add_tag normalizes to title case, so "isracard" becomes "Isracard"
        assert any("Isracard" in tag for tag in cc_tags)
