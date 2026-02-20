"""Tagging service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for category and tag management.
"""

from copy import deepcopy
from typing import Optional

from sqlalchemy.orm import Session

from backend.constants.categories import PROTECTED_CATEGORIES
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import (
    CreditCardRepository,
    TransactionsRepository,
)
from backend.utils.text_utils import to_title_case


# In-memory cache for categories
_categories_cache: Optional[dict] = None


class CategoriesTagsService:
    """Service for managing categories and tags."""

    def __init__(self, db: Session):
        self.db = db
        self.tagging_repo = TaggingRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.split_transactions_repo = SplitTransactionsRepository(db)
        self.tagging_rules_repo = TaggingRulesRepository(db)
        self.credit_card_repo = CreditCardRepository(db)
        self.categories_and_tags = self.get_categories_and_tags()

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """Load categories and tags with caching."""
        global _categories_cache

        if _categories_cache is None:
            _categories_cache = self.tagging_repo.get_categories()

        if copy:
            return deepcopy(_categories_cache)
        return _categories_cache

    def _invalidate_cache(self) -> None:
        """Clear cache and reload from DB."""
        global _categories_cache
        _categories_cache = None
        self.categories_and_tags = self.get_categories_and_tags()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory categories cache."""
        global _categories_cache
        _categories_cache = None

    def get_categories_icons(self) -> dict[str, str]:
        """Load category icons."""
        return self.tagging_repo.get_categories_icons()

    def update_category_icon(self, category: str, icon: str) -> bool:
        """Set or update the icon for a category."""
        return self.tagging_repo.update_category_icon(category, icon)

    def add_category(self, category: str, tags: list[str]) -> bool:
        """Add a new category. Returns True if added successfully."""
        if not category or not isinstance(category, str) or not category.strip():
            return False
        category = to_title_case(category.strip())
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.tagging_repo.add_category(category, tags)
        self._invalidate_cache()
        return True

    def delete_category(self, category: str) -> bool:
        """Delete a category. Returns True if deleted successfully."""
        if category in PROTECTED_CATEGORIES:
            return False

        self.transactions_repo.nullify_category(category)
        self.split_transactions_repo.nullify_category(category)
        self.tagging_rules_repo.delete_rules_by_category(category)

        if category not in self.categories_and_tags:
            return False
        self.tagging_repo.delete_category(category)
        self._invalidate_cache()
        return True

    def reallocate_tag(self, old_category: str, new_category: str, tag: str) -> bool:
        """Move a tag from one category to another."""
        if (
            old_category not in self.categories_and_tags
            or new_category not in self.categories_and_tags
        ):
            return False

        self.transactions_repo.update_category_for_tag(
            old_category, new_category, tag
        )
        self.split_transactions_repo.update_category_for_tag(
            old_category, new_category, tag
        )
        self.tagging_rules_repo.update_category_for_tag(
            old_category, new_category, tag
        )

        self.tagging_repo.relocate_tag(tag, old_category, new_category)
        self._invalidate_cache()
        return True

    def add_tag(self, category: str, tag: str) -> bool:
        """Add a new tag to a category."""
        if category not in self.categories_and_tags:
            return False
        tag = to_title_case(tag.strip()) if tag else tag
        if tag in self.categories_and_tags[category]:
            return False
        self.tagging_repo.add_tag(category, tag)
        self._invalidate_cache()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        """Delete a tag from a category."""
        self.transactions_repo.nullify_category_and_tag(category, tag)
        self.split_transactions_repo.nullify_category_and_tag(category, tag)
        self.tagging_rules_repo.delete_rules_by_category_and_tag(category, tag)

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.tagging_repo.delete_tag(category, tag)
        self._invalidate_cache()
        return True

    def add_new_credit_card_tags(self) -> bool:
        """Add new credit card tags to the Credit Cards category."""
        cc_accounts = self.credit_card_repo.get_unique_accounts_tags()
        if "Credit Cards" not in self.categories_and_tags:
            self.add_category("Credit Cards", cc_accounts)
            return True
        for account in cc_accounts:
            self.add_tag("Credit Cards", account)
        return True
