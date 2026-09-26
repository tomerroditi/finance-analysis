"""Business logic for category and tag management."""

from copy import deepcopy
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PROTECTED_CATEGORIES,
    PROTECTED_TAGS,
    UNUSED_CATEGORY_MONTHS,
)
from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions import (
    CreditCardRepository,
    TransactionsRepository,
)
from backend.utils.db_path_cache import cache_key
from backend.utils.text_utils import to_title_case

# In-memory categories cache, partitioned by the resolved database path
# (see ``backend.utils.db_path_cache``).
_categories_cache: dict[str, dict[str, list[str]]] = {}


def _clean_name(name: object) -> str | None:
    """Normalise a category/tag name, or return ``None`` if it is unusable.

    A usable name is a non-blank string without ``;`` — budget rules store
    tag lists as ``"tag1;tag2"``, so a semicolon inside a name would split
    into two tags the moment it reached a budget.

    Parameters
    ----------
    name : object
        Raw user-supplied name.

    Returns
    -------
    str or None
        The stripped, title-cased name, or ``None`` when rejected.
    """
    if not isinstance(name, str) or not name.strip() or ";" in name:
        return None
    return to_title_case(name.strip())


class CategoriesTagsService:
    """Service for managing the categories and tags hierarchy.

    Categories and their associated tags are stored in the database and
    cached in memory via ``_categories_cache``. All mutation operations
    invalidate the cache after persisting changes. The in-memory
    ``categories_and_tags`` attribute is kept in sync with the cache.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.tagging_repo = TaggingRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.split_transactions_repo = SplitTransactionsRepository(db)
        self.tagging_rules_repo = TaggingRulesRepository(db)
        self.credit_card_repo = CreditCardRepository(db)
        self.budget_repo = BudgetRepository(db)
        self.categories_and_tags = self.get_categories_and_tags()

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """Load categories and tags from the database with in-memory caching.

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
        key = cache_key()
        if key not in _categories_cache:
            _categories_cache[key] = self.tagging_repo.get_categories()

        if copy:
            return deepcopy(_categories_cache[key])
        return _categories_cache[key]

    def _invalidate_cache(self) -> None:
        """Clear the current context's cache entry and reload from the DB."""
        _categories_cache.pop(cache_key(), None)
        self.categories_and_tags = self.get_categories_and_tags()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory categories cache for every partition."""
        _categories_cache.clear()

    @staticmethod
    def clear_cache_for(db_path: str) -> None:
        """Drop the cache entry of one database file (replaced on disk)."""
        _categories_cache.pop(db_path, None)

    def get_categories_icons(self) -> dict[str, str]:
        """Load the category icons.

        Returns
        -------
        dict[str, str]
            Mapping of category name to emoji icon string; categories without
            an icon are omitted.
        """
        return self.tagging_repo.get_categories_icons()

    def get_category_usage(self) -> dict[str, dict[str, Any]]:
        """Return per-category usage info and the unused verdict.

        A category is unused when it has had no transaction for
        ``UNUSED_CATEGORY_MONTHS`` months, was itself created longer ago than
        that, and is not protected. The creation grace stops a freshly added
        category — which has no transactions by definition — from being
        demoted the moment it is created.

        Returns
        -------
        dict[str, dict[str, Any]]
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

        usage: dict[str, dict[str, Any]] = {}
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
        """Set or update the emoji icon for a category.

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
        """Add a new category with an initial list of tags.

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
            ``True`` if the category was created, ``False`` if rejected —
            blank or ``;``-containing names (category or any tag), or a
            category that already exists.
        """
        category = _clean_name(category)
        if category is None:
            return False
        if category.lower() in [k.lower() for k in self.categories_and_tags]:
            return False
        clean_tags: list[str] = []
        for tag in tags or []:
            tag = _clean_name(tag)
            if tag is None:
                return False
            if tag not in clean_tags:
                clean_tags.append(tag)
        self.tagging_repo.add_category(category, clean_tags)
        self._invalidate_cache()
        return True

    def delete_category(self, category: str) -> None:
        """Delete a category and nullify it on all related transactions and rules.

        Protected categories (``PROTECTED_CATEGORIES``) cannot be deleted.
        All transactions and split transactions referencing this category
        have their category set to ``NULL``. Associated tagging rules are
        also deleted.

        Parameters
        ----------
        category : str
            Name of the category to delete.

        Raises
        ------
        EntityNotFoundException
            If no such category exists.
        ValidationException
            If the category is protected. Nothing is touched when either is
            raised.
        """
        if category not in self.categories_and_tags:
            raise EntityNotFoundException(f"Category '{category}' not found")
        if category in PROTECTED_CATEGORIES:
            raise ValidationException(
                f"Category '{category}' is protected and cannot be deleted"
            )

        self.transactions_repo.nullify_category(category)
        self.split_transactions_repo.nullify_category(category)
        self.tagging_rules_repo.delete_rules_by_category(category)
        self.tagging_repo.delete_category(category)
        self._invalidate_cache()

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
            True if renamed, False if protected, not found, blank/invalid,
            or colliding with another category. Renaming a category to its
            own name is a no-op that returns True.
        """
        if old_name in PROTECTED_CATEGORIES:
            return False
        if old_name not in self.categories_and_tags:
            return False

        new_name = _clean_name(new_name)
        if new_name is None:
            return False
        if new_name == old_name:
            return True
        if new_name.lower() != old_name.lower() and new_name.lower() in [
            k.lower() for k in self.categories_and_tags
        ]:
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
            True if renamed, False if protected, not found, blank/invalid, or
            colliding with a sibling tag. Renaming a tag to its own name is a
            no-op that returns True.
        """
        if old_tag in PROTECTED_TAGS:
            return False
        if category not in self.categories_and_tags:
            return False
        if old_tag not in self.categories_and_tags[category]:
            return False

        new_tag = _clean_name(new_tag)
        if new_tag is None:
            return False
        if new_tag == old_tag:
            return True
        if new_tag in self.categories_and_tags[category]:
            return False

        self.transactions_repo.rename_tag(category, old_tag, new_tag)
        self.split_transactions_repo.rename_tag(category, old_tag, new_tag)
        self.tagging_rules_repo.rename_tag(category, old_tag, new_tag)
        self.budget_repo.rename_tag(category, old_tag, new_tag)
        self.tagging_repo.rename_tag(category, old_tag, new_tag)
        self._invalidate_cache()
        return True

    def reallocate_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """Move a tag from one category to another.

        Updates transactions, split transactions, tagging rules and budget
        rules to use the new category, then moves the tag itself.

        Parameters
        ----------
        old_category : str
            Current category the tag belongs to.
        new_category : str
            Target category to move the tag into.
        tag : str
            Tag to relocate.

        Raises
        ------
        EntityNotFoundException
            If either category does not exist, or the tag is not in
            ``old_category``.
        ValidationException
            If both categories are the same. Nothing is touched when either
            is raised.
        """
        categories = self.categories_and_tags
        if old_category not in categories or new_category not in categories:
            raise EntityNotFoundException("Category not found")
        if tag not in categories[old_category]:
            raise EntityNotFoundException(
                f"Tag '{tag}' not found in category '{old_category}'"
            )
        if old_category == new_category:
            raise ValidationException(
                f"Cannot move tag '{tag}' from '{old_category}' to itself"
            )

        self.transactions_repo.update_category_for_tag(old_category, new_category, tag)
        self.split_transactions_repo.update_category_for_tag(
            old_category, new_category, tag
        )
        self.tagging_rules_repo.update_category_for_tag(old_category, new_category, tag)
        self.budget_repo.reallocate_tag(old_category, new_category, tag)

        self.tagging_repo.relocate_tag(tag, old_category, new_category)
        self._invalidate_cache()

    def add_tag(self, category: str, tag: str) -> None:
        """Add a new tag to an existing category.

        The tag is normalised to title case.

        Parameters
        ----------
        category : str
            Category to add the tag to.
        tag : str
            Tag name to add.

        Raises
        ------
        EntityNotFoundException
            If the category does not exist.
        ValidationException
            If the tag name is blank or contains ``;``, or the tag already
            exists in the category.
        """
        if category not in self.categories_and_tags:
            raise EntityNotFoundException(f"Category '{category}' not found")
        if not self._add_tag_if_new(category, tag):
            raise ValidationException(
                f"Cannot add tag '{tag}' to '{category}'. The name may be "
                "blank or invalid, or the tag may already exist."
            )

    def _add_tag_if_new(self, category: str, tag: str) -> bool:
        """Add ``tag`` to an existing ``category`` unless it is unusable or present.

        The non-raising path for internal callers (credit-card tag discovery)
        that treat "already exists" as success rather than an error.

        Parameters
        ----------
        category : str
            Existing category to add the tag to.
        tag : str
            Tag name to add; normalised to title case.

        Returns
        -------
        bool
            ``True`` if the tag was added, ``False`` if it was blank,
            ``;``-containing, or already present.
        """
        tag = _clean_name(tag)
        if tag is None or tag in self.categories_and_tags[category]:
            return False
        self.tagging_repo.add_tag(category, tag)
        self._invalidate_cache()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        """Delete a tag from a category and nullify it on related transactions and rules.

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
            does not exist. Nothing is touched when ``False`` is returned.
        """
        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False

        self.transactions_repo.nullify_category_and_tag(category, tag)
        self.split_transactions_repo.nullify_category_and_tag(category, tag)
        self.tagging_rules_repo.delete_rules_by_category_and_tag(category, tag)
        self.tagging_repo.delete_tag(category, tag)
        self._invalidate_cache()
        return True

    def add_new_credit_card_tags(self) -> bool:
        """Add new credit card account tags to the ``Credit Cards`` category.

        Queries unique ``provider - account_name - account_number`` combinations
        from credit card transactions and adds any that are not already present
        as tags under ``Credit Cards``. Creates the category if it does not exist.
        Tags are title-cased on both paths (``"isracard - main - 1234"`` becomes
        ``"Isracard - Main - 1234"``) so a second discovery never adds a
        case-variant duplicate; ``auto_tag_credit_cards_bills`` matches them
        back to the raw rows case-insensitively.

        Returns
        -------
        bool
            Always ``True``.
        """
        cc_accounts = [
            to_title_case(account)
            for account in self.credit_card_repo.get_unique_accounts_tags()
        ]
        if "Credit Cards" not in self.categories_and_tags:
            self.add_category("Credit Cards", cc_accounts)
            return True
        for account in cc_accounts:
            self._add_tag_if_new("Credit Cards", account)
        return True
