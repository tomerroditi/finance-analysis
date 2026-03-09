"""Tests for category and tag renaming functionality.

Validates the CategoriesTagsService.rename_category and rename_tag methods,
including protection checks, collision detection, title-casing, and cascade
to all dependent repositories.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.services.tagging_service import CategoriesTagsService
from backend.constants.categories import PROTECTED_CATEGORIES, PROTECTED_TAGS


def _make_service(categories_and_tags: dict) -> CategoriesTagsService:
    """Create a CategoriesTagsService with mocked dependencies.

    Parameters
    ----------
    categories_and_tags : dict
        Category-to-tags mapping to use as the service's config.

    Returns
    -------
    CategoriesTagsService
        Service instance with all repos replaced by MagicMocks.
    """
    with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
        service = CategoriesTagsService(None)
    service.categories_and_tags = categories_and_tags
    service.tagging_repo = MagicMock()
    service.transactions_repo = MagicMock()
    service.split_transactions_repo = MagicMock()
    service.tagging_rules_repo = MagicMock()
    service.budget_repo = MagicMock()
    service._invalidate_cache = MagicMock()
    return service


class TestRenameCategory:
    """Tests for CategoriesTagsService.rename_category."""

    def test_protected_category_returns_false(self):
        """Renaming a protected category should return False."""
        for cat in PROTECTED_CATEGORIES:
            service = _make_service({cat: []})
            assert service.rename_category(cat, "New Name") is False

    def test_nonexistent_category_returns_false(self):
        """Renaming a category not in the config should return False."""
        service = _make_service({"Food": []})
        assert service.rename_category("NonExistent", "New Name") is False

    def test_collision_returns_false(self):
        """Renaming to an existing category name should return False."""
        service = _make_service({"Food": [], "Shopping": []})
        assert service.rename_category("Food", "Shopping") is False

    def test_case_insensitive_collision(self):
        """Renaming to an existing name differing only in case should return False."""
        service = _make_service({"Food": [], "Shopping": []})
        assert service.rename_category("Food", "shopping") is False

    def test_empty_name_returns_false(self):
        """Renaming to empty string should return False."""
        service = _make_service({"Food": []})
        assert service.rename_category("Food", "  ") is False

    def test_successful_rename_cascades(self):
        """Successful rename should cascade to all repos and invalidate cache."""
        service = _make_service({"Food": ["Groceries"]})
        result = service.rename_category("Food", "Dining")
        assert result is True
        service.transactions_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.split_transactions_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.tagging_rules_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.budget_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.tagging_repo.rename_category.assert_called_once_with("Food", "Dining")
        service._invalidate_cache.assert_called_once()

    def test_rename_applies_title_case(self):
        """New name should be title-cased."""
        service = _make_service({"Food": []})
        service.rename_category("Food", "my dining")
        service.tagging_repo.rename_category.assert_called_once_with("Food", "My Dining")

    def test_same_case_change_allowed(self):
        """Renaming to same name with different casing should be allowed."""
        service = _make_service({"food stuff": []})
        result = service.rename_category("food stuff", "Food Stuff")
        assert result is True


class TestRenameTag:
    """Tests for CategoriesTagsService.rename_tag."""

    def test_protected_tag_returns_false(self):
        """Renaming a protected tag should return False."""
        for tag in PROTECTED_TAGS:
            service = _make_service({"Other Income": [tag]})
            assert service.rename_tag("Other Income", tag, "New Tag") is False

    def test_nonexistent_category_returns_false(self):
        """Renaming a tag in a nonexistent category should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("NonExistent", "Groceries", "New Tag") is False

    def test_nonexistent_tag_returns_false(self):
        """Renaming a tag that doesn't exist should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("Food", "NonExistent", "New Tag") is False

    def test_collision_returns_false(self):
        """Renaming to an existing tag in same category should return False."""
        service = _make_service({"Food": ["Groceries", "Restaurants"]})
        assert service.rename_tag("Food", "Groceries", "Restaurants") is False

    def test_empty_name_returns_false(self):
        """Renaming to empty string should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("Food", "Groceries", "  ") is False

    def test_successful_rename_cascades(self):
        """Successful rename should cascade to all repos and invalidate cache."""
        service = _make_service({"Food": ["Groceries"]})
        result = service.rename_tag("Food", "Groceries", "Supermarket")
        assert result is True
        service.transactions_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.split_transactions_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.tagging_rules_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.budget_repo.rename_tag.assert_called_once_with("Groceries", "Supermarket")
        service.tagging_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service._invalidate_cache.assert_called_once()

    def test_rename_applies_title_case(self):
        """New tag name should be title-cased."""
        service = _make_service({"Food": ["Groceries"]})
        service.rename_tag("Food", "Groceries", "organic food")
        service.tagging_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Organic Food")
