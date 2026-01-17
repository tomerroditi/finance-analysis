"""
Tagging service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for category and tag management.
"""

from copy import deepcopy
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import TransactionsRepository


def _sorted_unique(lst: list) -> list:
    """Create a sorted list of unique elements."""
    return sorted(list(set(lst)))


# In-memory cache for categories (replaces Streamlit session_state)
_categories_cache: Optional[dict] = None


class CategoriesTagsService:
    """
    Service for managing categories and tags.

    Provides methods for adding, deleting, and managing categories and tags,
    including tag reallocation between categories.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize the CategoriesTagsService.

        Parameters
        ----------
        db : Session, optional
            SQLAlchemy session for database operations.
            If None, only file-based operations are available.
        """
        self.db = db
        self.categories_and_tags = self.get_categories_and_tags()

        # Only initialize repos if db is provided
        if db is not None:
            self.transactions_repo = TransactionsRepository(db)
            self.split_transactions_repo = SplitTransactionsRepository(db)
            self.tagging_rules_repo = TaggingRulesRepository(db)
        else:
            self.transactions_repo = None
            self.split_transactions_repo = None
            self.tagging_rules_repo = None

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """
        Load categories and tags with caching.

        Uses in-memory cache instead of Streamlit session state.
        """
        global _categories_cache

        if _categories_cache is None:
            _categories_cache = TaggingRepository.get_categories()

        if copy:
            return deepcopy(_categories_cache)
        return _categories_cache

    def save_categories_and_tags(self) -> None:
        """Save categories and tags to file and update cache."""
        global _categories_cache
        _categories_cache = self.categories_and_tags
        TaggingRepository.save_categories_to_file(
            self.categories_and_tags, AppConfig().get_categories_path()
        )

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory categories cache."""
        global _categories_cache
        _categories_cache = None

    def get_categories_icons(self) -> dict[str, str]:
        """Load category icons."""
        return TaggingRepository.get_categories_icons()

    def update_category_icon(self, category: str, icon: str) -> bool:
        """Set or update the icon for a category."""
        return TaggingRepository.update_category_icon(category, icon)

    def add_category(self, category: str) -> bool:
        """
        Add a new category.

        Returns True if added successfully, False if empty or already exists.
        """
        if not category or not isinstance(category, str) or not category.strip():
            return False
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.categories_and_tags[category] = []
        self.save_categories_and_tags()
        return True

    def delete_category(self, category: str, protected_categories: List[str]) -> bool:
        """
        Delete a category.

        Returns True if deleted successfully, False if protected or doesn't exist.
        """
        # Update database if repos are available
        if self.transactions_repo:
            self.transactions_repo.nullify_category(category)
        if self.split_transactions_repo:
            self.split_transactions_repo.nullify_category(category)
        if self.tagging_rules_repo:
            self.tagging_rules_repo.delete_rules_by_category(category)

        if category in protected_categories:
            return False
        if category in self.categories_and_tags:
            del self.categories_and_tags[category]
            self.save_categories_and_tags()
            return True
        return False

    def reallocate_tags(
        self, old_category: str, new_category: str, tags: List[str]
    ) -> bool:
        """
        Move tags from one category to another.

        Returns True if successful, False if either category doesn't exist.
        """
        if (
            old_category not in self.categories_and_tags
            or new_category not in self.categories_and_tags
        ):
            return False

        # Update category for the specified tags in all relevant tables
        for tag in tags:
            if self.transactions_repo:
                self.transactions_repo.update_category_for_tag(
                    old_category, new_category, tag
                )
            if self.split_transactions_repo:
                self.split_transactions_repo.update_category_for_tag(
                    old_category, new_category, tag
                )
            if self.tagging_rules_repo:
                self.tagging_rules_repo.update_category_for_tag(
                    old_category, new_category, tag
                )

        # Remove tags from old category
        self.categories_and_tags[old_category] = [
            t for t in self.categories_and_tags[old_category] if t not in tags
        ]
        # Add tags to new category (avoid duplicates)
        self.categories_and_tags[new_category] = _sorted_unique(
            self.categories_and_tags[new_category] + tags
        )
        self.save_categories_and_tags()
        return True

    def add_tag(self, category: str, tag: str) -> bool:
        """
        Add a new tag to a category.

        Returns True if added successfully, False if category doesn't exist or tag exists.
        """
        if category not in self.categories_and_tags:
            return False
        if tag in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].append(tag)
        self.save_categories_and_tags()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        """
        Delete a tag from a category.

        Also nullifies the tag in transactions and removes related tagging rules.
        """
        # Update database if repos are available
        if self.transactions_repo:
            self.transactions_repo.nullify_category_and_tag(category, tag)
        if self.split_transactions_repo:
            self.split_transactions_repo.nullify_category_and_tag(category, tag)
        if self.tagging_rules_repo:
            self.tagging_rules_repo.delete_rules_by_category_and_tag(category, tag)

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].remove(tag)
        self.save_categories_and_tags()
        return True
