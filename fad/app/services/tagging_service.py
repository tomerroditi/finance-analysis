from typing import List
import os

import streamlit as st
from streamlit.connections import SQLConnection

from fad import CATEGORIES_PATH, SRC_PATH
from fad.app.data_access import get_db_connection
from fad.app.data_access.tagging_repository import TaggingRepository
from fad.app.data_access.tagging_rules_repository import TaggingRulesRepository
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository


def _sorted_unique(lst):
    """
    Create a sorted list of unique elements from the input list.

    Parameters
    ----------
    lst : list
        The input list that may contain duplicate elements.

    Returns
    -------
    list
        A new list containing unique elements from the input list, sorted in ascending order.
    """
    return sorted(list(set(lst)))


class CategoriesTagsService:
    """
    Service for managing categories and tags in the application.

    This class provides methods for adding, deleting, and managing categories and tags,
    as well as reallocating tags between categories. It maintains the categories and tags
    in both the session state and persistent storage.

    Attributes
    ----------
    categories_and_tags : dict
        Dictionary mapping category names to lists of tag names.
    """
    def __init__(self):
        """
        Initialize the CategoriesTagsService.

        Loads the categories and tags using business logic for file management,
        session state management, and default loading.
        """
        self.categories_and_tags = self.get_categories_and_tags()
        conn = get_db_connection()
        self.transactions_repo = TransactionsRepository(conn)
        self.split_transactions_repo = SplitTransactionsRepository(conn)
        self.tagging_rules_repo = TaggingRulesRepository(conn)

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """
        Load categories and tags with business logic for file and session state management.

        This method contains the business logic that was moved from TaggingRepository.
        It handles file existence checking, default loading, and session state management.
        """
        if 'categories_and_tags' not in st.session_state:
            if not TaggingRepository.file_exists(CATEGORIES_PATH):
                TaggingRepository.create_directory(os.path.dirname(CATEGORIES_PATH))
                default_categories = TaggingRepository.load_categories_from_file(
                    os.path.join(SRC_PATH, 'resources', 'default_categories.yaml')
                )
                TaggingRepository.save_categories_to_file(default_categories, CATEGORIES_PATH)

            st.session_state['categories_and_tags'] = TaggingRepository.load_categories_from_file(CATEGORIES_PATH)

        if copy:
            from copy import deepcopy
            return deepcopy(st.session_state['categories_and_tags'])
        return st.session_state['categories_and_tags']

    def save_categories_and_tags(self) -> None:
        """
        Save categories and tags with business logic for session state and file management.

        This method contains the business logic that was moved from TaggingRepository.
        Uses the class property categories_and_tags directly.
        """
        st.session_state['categories_and_tags'] = self.categories_and_tags
        TaggingRepository.save_categories_to_file(self.categories_and_tags, CATEGORIES_PATH)

    def add_category(self, category: str) -> bool:
        """
        Add a new category to the categories and tags dictionary.

        Parameters
        ----------
        category : str
            The name of the category to add.

        Returns
        -------
        bool
            True if the category was successfully added, False otherwise.
            Returns False if the category is empty, not a string, or already exists.
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
        Delete a category from the categories and tags dictionary.

        Parameters
        ----------
        category : str
            The name of the category to delete.
        protected_categories : List[str]
            List of category names that cannot be deleted.

        Returns
        -------
        bool
            True if the category was successfully deleted, False otherwise.
            Returns False if the category is protected or doesn't exist.
        """
        # Delete category from db data
        self.transactions_repo.nullify_category(category)
        self.split_transactions_repo.nullify_category(category)
        self.tagging_rules_repo.delete_rules_by_category(category)
        if category in protected_categories:
            return False
        if category in self.categories_and_tags:
            del self.categories_and_tags[category]
            self.save_categories_and_tags()
            return True
        return False

    def reallocate_tags(self, old_category: str, new_category: str, tags: List[str]) -> bool:
        """
        Move tags from one category to another.

        Parameters
        ----------
        old_category : str
            The name of the category from which to move tags.
        new_category : str
            The name of the category to which to move tags.
        tags : List[str]
            List of tag names to move.

        Returns
        -------
        bool
            True if the tags were successfully reallocated, False otherwise.
            Returns False if either category doesn't exist.
        """
        # Update category for the specified tags in all relevant tables
        for tag in tags:
            self.transactions_repo.update_category_for_tag(old_category, new_category, tag)
            self.split_transactions_repo.update_category_for_tag(old_category, new_category, tag)
            self.tagging_rules_repo.update_category_for_tag(old_category, new_category, tag)
        # Remove tags from old category
        self.categories_and_tags[old_category] = [t for t in self.categories_and_tags[old_category] if t not in tags]
        # Add tags to new category (avoid duplicates)
        self.categories_and_tags[new_category] = _sorted_unique(self.categories_and_tags[new_category] + tags)
        self.save_categories_and_tags()
        return True

    def add_tag(self, category: str, tag: str) -> bool:
        """
        Add a new tag to a category.

        Parameters
        ----------
        category : str
            The name of the category to which to add the tag.
        tag : str
            The name of the tag to add.

        Returns
        -------
        bool
            True if the tag was successfully added, False otherwise.
            Returns False if the category doesn't exist or the tag already exists in the category.
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

        Parameters
        ----------
        category : str
            The name of the category from which to delete the tag.
        tag : str
            The name of the tag to delete.

        Returns
        -------
        bool
            True if the tag was successfully deleted, False otherwise.
            Returns False if the category doesn't exist or the tag doesn't exist in the category.
        """
        # 1. Set category and tag to null in transactions table (credit_card and bank)
        self.transactions_repo.nullify_category_and_tag(category, tag)

        # 2. Set category and tag to null in split transactions table (both services)
        self.split_transactions_repo.nullify_category_and_tag(category, tag)

        # 3. Remove rules with the specified category and tag from the tagging rules table
        self.tagging_rules_repo.delete_rules_by_category_and_tag(category, tag)

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].remove(tag)
        self.save_categories_and_tags()
        return True

