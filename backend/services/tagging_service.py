"""Tagging service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for category and tag management.
"""

from copy import deepcopy
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.constants.categories import (
    PROTECTED_CATEGORIES,
    PROTECTED_TAGS,
    UNUSED_CATEGORY_MONTHS,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import (
    CreditCardRepository,
    TransactionsRepository,
)
from backend.utils.text_utils import to_title_case


# In-memory categories cache, partitioned by demo mode — demo and real
# categories live in different databases and must not evict each other.
_categories_cache: dict[bool, dict] = {}


class CategoriesTagsService:
    """
    Service for managing the categories and tags hierarchy.

    Categories and their associated tags are stored in a YAML file and
    cached in memory via ``_categories_cache``. All mutation operations
    invalidate the cache after persisting changes. The in-memory
    ``categories_and_tags`` attribute is kept in sync with the cache.
    """

    def __init__(self, db: Session):
        """
        Initialize the categories/tags service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.tagging_repo = TaggingRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.split_transactions_repo = SplitTransactionsRepository(db)
        self.tagging_rules_repo = TaggingRulesRepository(db)
        self.credit_card_repo = CreditCardRepository(db)
        self.budget_repo = BudgetRepository(db)
        self.categories_and_tags = self.get_categories_and_tags()

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """
        Load categories and tags from the YAML file with in-memory caching.

        Parameters
        ----------
        copy : bool, optional
            When ``True``, returns a deep copy so callers can mutate the
            result without affecting the cache. Default is ``False``.

        Returns
        -------
        dict[str, list[str]]
            Mapping of category name to list of tag names.
        """
        global _categories_cache

        mode = AppConfig().is_demo_mode
        if mode not in _categories_cache:
            _categories_cache[mode] = self.tagging_repo.get_categories()

        if copy:
            return deepcopy(_categories_cache[mode])
        return _categories_cache[mode]

    def _invalidate_cache(self) -> None:
        """Clear the current mode's cache entry and reload from the DB."""
        global _categories_cache
        _categories_cache.pop(AppConfig().is_demo_mode, None)
        self.categories_and_tags = self.get_categories_and_tags()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory categories cache for every mode."""
        global _categories_cache
        _categories_cache.clear()

    def get_categories_icons(self) -> dict[str, str]:
        """
        Load category icons from the icons YAML file.

        Returns
        -------
        dict[str, str]
            Mapping of category name to emoji icon string.
        """
        return self.tagging_repo.get_categories_icons()

    def get_category_usage(self) -> dict[str, dict]:
        """Return per-category usage info and the unused verdict.

        A category is unused when it has had no transaction for
        ``UNUSED_CATEGORY_MONTHS`` months, was itself created longer ago than
        that, and is not protected. The creation grace stops a freshly added
        category — which has no transactions by definition — from being
        demoted the moment it is created.

        Returns
        -------
        dict[str, dict]
            Mapping of category name to ``{"last_used": str | None,
            "unused": bool}``. ``last_used`` is a ``YYYY-MM-DD`` string, or
            ``None`` when the category has never been used.
        """
        cutoff = (
            pd.Timestamp.today().normalize()
            - pd.DateOffset(months=UNUSED_CATEGORY_MONTHS)
        ).date()

        last_used_map = self.transactions_repo.get_category_last_used()
        created_at_map = self.tagging_repo.get_categories_created_at()

        usage: dict[str, dict] = {}
        for name in self.get_categories_and_tags():
            last_used = last_used_map.get(name)
            created_at = created_at_map.get(name)
            created_before_cutoff = (
                created_at is not None and created_at.date() < cutoff
            )
            used_recently = (
                last_used is not None and date.fromisoformat(last_used) >= cutoff
            )
            usage[name] = {
                "last_used": last_used,
                "unused": (
                    name not in PROTECTED_CATEGORIES
                    and created_before_cutoff
                    and not used_recently
                ),
            }
        return usage

    def update_category_icon(self, category: str, icon: str) -> bool:
        """
        Set or update the emoji icon for a category.

        Parameters
        ----------
        category : str
            Category name to update.
        icon : str
            Emoji or icon string to associate with the category.

        Returns
        -------
        bool
            ``True`` if the icon was saved successfully.
        """
        return self.tagging_repo.update_category_icon(category, icon)

    def add_category(self, category: str, tags: list[str]) -> bool:
        """
        Add a new category with an initial list of tags.

        The category name is normalised to title case. Returns ``False``
        if the name is blank or already exists (case-insensitive match).

        Parameters
        ----------
        category : str
            Name of the new category.
        tags : list[str]
            Initial tags to add under the category.

        Returns
        -------
        bool
            ``True`` if the category was created, ``False`` if rejected.
        """
        if not category or not isinstance(category, str) or not category.strip():
            return False
        category = to_title_case(category.strip())
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.tagging_repo.add_category(category, tags)
        self._invalidate_cache()
        return True

    def delete_category(self, category: str) -> bool:
        """
        Delete a category and nullify it on all related transactions and rules.

        Protected categories (``PROTECTED_CATEGORIES``) cannot be deleted.
        All transactions and split transactions referencing this category
        have their category set to ``NULL``. Associated tagging rules are
        also deleted.

        Parameters
        ----------
        category : str
            Name of the category to delete.

        Returns
        -------
        bool
            ``True`` if the category was deleted, ``False`` if it is protected
            or not found in the YAML config.
        """
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

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Rename a category and cascade across all tables.

        Parameters
        ----------
        old_name : str
            Current category name.
        new_name : str
            New category name (will be title-cased).

        Returns
        -------
        bool
            True if renamed, False if protected or not found.
        """
        if old_name in PROTECTED_CATEGORIES:
            return False
        if old_name not in self.categories_and_tags:
            return False

        new_name = to_title_case(new_name.strip()) if new_name else new_name
        if not new_name:
            return False
        if new_name.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            if new_name.lower() != old_name.lower():
                return False

        self.transactions_repo.rename_category(old_name, new_name)
        self.split_transactions_repo.rename_category(old_name, new_name)
        self.tagging_rules_repo.rename_category(old_name, new_name)
        self.budget_repo.rename_category(old_name, new_name)
        self.tagging_repo.rename_category(old_name, new_name)
        self._invalidate_cache()
        return True

    def rename_tag(self, category: str, old_tag: str, new_tag: str) -> bool:
        """Rename a tag and cascade across all tables.

        Parameters
        ----------
        category : str
            Category the tag belongs to.
        old_tag : str
            Current tag name.
        new_tag : str
            New tag name (will be title-cased).

        Returns
        -------
        bool
            True if renamed, False if protected, not found, or collision.
        """
        if old_tag in PROTECTED_TAGS:
            return False
        if category not in self.categories_and_tags:
            return False
        if old_tag not in self.categories_and_tags[category]:
            return False

        new_tag = to_title_case(new_tag.strip()) if new_tag else new_tag
        if not new_tag:
            return False
        if new_tag in self.categories_and_tags[category]:
            if new_tag != old_tag:
                return False

        self.transactions_repo.rename_tag(category, old_tag, new_tag)
        self.split_transactions_repo.rename_tag(category, old_tag, new_tag)
        self.tagging_rules_repo.rename_tag(category, old_tag, new_tag)
        self.budget_repo.rename_tag(old_tag, new_tag)
        self.tagging_repo.rename_tag(category, old_tag, new_tag)
        self._invalidate_cache()
        return True

    def reallocate_tag(self, old_category: str, new_category: str, tag: str) -> bool:
        """
        Move a tag from one category to another.

        Updates transactions, split transactions, and tagging rules to use
        the new category, then moves the tag in the YAML config.

        Parameters
        ----------
        old_category : str
            Current category the tag belongs to.
        new_category : str
            Target category to move the tag into.
        tag : str
            Tag to relocate.

        Returns
        -------
        bool
            ``True`` if the tag was moved, ``False`` if either category does
            not exist in the current config.
        """
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
        """
        Add a new tag to an existing category.

        The tag is normalised to title case. Returns ``False`` if the category
        does not exist or the tag is already present.

        Parameters
        ----------
        category : str
            Category to add the tag to.
        tag : str
            Tag name to add.

        Returns
        -------
        bool
            ``True`` if the tag was added, ``False`` if rejected.
        """
        if category not in self.categories_and_tags:
            return False
        tag = to_title_case(tag.strip()) if tag else tag
        if tag in self.categories_and_tags[category]:
            return False
        self.tagging_repo.add_tag(category, tag)
        self._invalidate_cache()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        """
        Delete a tag from a category and nullify it on related transactions and rules.

        Transactions and split transactions with the matching category/tag have
        both fields set to ``NULL``. Associated tagging rules are deleted.

        Parameters
        ----------
        category : str
            Category the tag belongs to.
        tag : str
            Tag to delete.

        Returns
        -------
        bool
            ``True`` if the tag was deleted, ``False`` if the category or tag
            does not exist in the current config.
        """
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
        """
        Add new credit card account tags to the ``Credit Cards`` category.

        Queries unique ``provider - account_name - account_number`` combinations
        from credit card transactions and adds any that are not already present
        as tags under ``Credit Cards``. Creates the category if it does not exist.

        Returns
        -------
        bool
            Always ``True``.
        """
        cc_accounts = self.credit_card_repo.get_unique_accounts_tags()
        if "Credit Cards" not in self.categories_and_tags:
            self.add_category("Credit Cards", cc_accounts)
            return True
        for account in cc_accounts:
            self.add_tag("Credit Cards", account)
        return True
