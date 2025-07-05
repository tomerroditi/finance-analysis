from typing import List, Tuple
from typing import Literal

import streamlit as st
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.tagging_repository import AutoTaggerRepository, TaggingRepository
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import (
    Tables,
    AutoTaggerTableFields,
    TransactionsTableFields,
)
from fad.app.services.transactions_service import TransactionsService

tags_table = Tables.AUTO_TAGGER.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
category_col = AutoTaggerTableFields.CATEGORY.value
tag_col = AutoTaggerTableFields.TAG.value
name_col = AutoTaggerTableFields.NAME.value
service_col = AutoTaggerTableFields.SERVICE.value
account_number_col = AutoTaggerTableFields.ACCOUNT_NUMBER.value


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

        Loads the categories and tags from the TaggingRepository.
        """
        self.tagging_repository = TaggingRepository()
        self.categories_and_tags = self.tagging_repository.get_categories_and_tags()

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
        self._save()
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
        # TODO: delete category from db data
        if category in protected_categories:
            return False
        if category in self.categories_and_tags:
            del self.categories_and_tags[category]
            self._save()
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
        # TODO: update tags within the database
        if old_category not in self.categories_and_tags or new_category not in self.categories_and_tags:
            return False
        # Remove tags from old category
        self.categories_and_tags[old_category] = [t for t in self.categories_and_tags[old_category] if t not in tags]
        # Add tags to new category (avoid duplicates)
        self.categories_and_tags[new_category] = _sorted_unique(self.categories_and_tags[new_category] + tags)
        self._save()
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
        self._save()
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
        # TODO: delete tag from db data

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].remove(tag)
        self._save()
        return True

    def _save(self):
        """
        Save the categories and tags to the session state and persistent storage.

        Updates the session state with the current categories_and_tags dictionary
        and saves the data to persistent storage using the TaggingRepository.
        """
        st.session_state['categories_and_tags'] = self.categories_and_tags
        TaggingRepository.save_categories_and_tags(self.categories_and_tags)


class AutomaticTaggerService:
    """
    Service for managing automatic tagging rules for financial transactions.

    This class provides methods for retrieving transactions without rules,
    adding and updating tagging rules, and applying rules to untagged transactions.

    Attributes
    ----------
    conn : SQLConnection
        Database connection object.
    auto_tagger_repo : AutoTaggerRepository
        Repository for automatic tagging operations.
    transactions_service : TransactionsService
        Service for transaction operations.
    """
    def __init__(self, conn: SQLConnection = get_db_connection()):
        """
        Initialize the AutomaticTaggerService.

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database.
        """
        self.conn = conn
        self.auto_tagger_repo = AutoTaggerRepository(conn)
        self.transactions_repo = TransactionsRepository(conn)
        self.transactions_service = TransactionsService(conn)

    def get_cc_without_rules(self) -> List[str]:
        """
        Get credit card transactions that do not have rules associated with them.

        Retrieves unique transaction descriptions from the credit card table that
        do not appear in the automatic tagging rules table.

        Returns
        -------
        List[str]
            A list of unique transaction descriptions without associated tagging rules.
        """
        # get all credit card transactions that do not apear in the auto tagger rules table
        auto_tagger_table = self.auto_tagger_repo.get_table("credit_card")
        cc_table = self.transactions_repo.get_table("credit_card")

        desc_col = TransactionsTableFields.DESCRIPTION.value
        cc_without_rules = cc_table.loc[~cc_table[desc_col].isin(auto_tagger_table[name_col]), desc_col].unique().tolist()

        return cc_without_rules

    def get_bank_without_rules(self) -> List[Tuple[str, str]]:
        """
        Get bank transactions that do not have rules associated with them.

        Retrieves unique combinations of transaction descriptions and account numbers
        from the bank table that do not appear in the automatic tagging rules table.

        Returns
        -------
        List[Tuple[str, str]]
            A list of tuples containing bank transactions without rules, 
            where each tuple is (description, account_number).
        """
        auto_tagger_table = self.auto_tagger_repo.get_table("bank")
        bank_table = self.transactions_repo.get_table("bank")

        desc_col = TransactionsTableFields.DESCRIPTION.value
        bank_account_number_col = TransactionsTableFields.ACCOUNT_NUMBER.value
        name_col = self.auto_tagger_repo.name_col
        auto_tagger_account_number_col = self.auto_tagger_repo.account_number_col

        bank_ids = bank_table[[desc_col, bank_account_number_col]].drop_duplicates()
        auto_ids = auto_tagger_table[[name_col, auto_tagger_account_number_col]].drop_duplicates()

        bank_set: set[Tuple[str, str]] = set(map(tuple, bank_ids.values))  # noqa
        auto_set: set[Tuple[str, str]] = set(map(tuple, auto_ids.values))  # noqa

        result = sorted(bank_set - auto_set)
        return result

    def get_bank_account_details(self, account_number: str) -> tuple[str, str]:
        """
        Get account name and provider details for a given bank account number.

        Queries the bank transactions table to retrieve the account name and provider
        associated with the specified account number.

        Parameters
        ----------
        account_number : str
            The bank account number to look up.

        Returns
        -------
        tuple
            A tuple containing (account_name, provider_name).
            Returns (None, None) if the account number is not found.
        """
        provider_col = TransactionsTableFields.PROVIDER.value
        account_number_col = TransactionsTableFields.ACCOUNT_NUMBER.value

        account_name_and_provider = self.conn.query(
            f"""
            SELECT {account_number_col}, {provider_col} 
            FROM {bank_table} 
            WHERE {account_number_col}=:account_number 
            LIMIT 1;
            """,
            params={'account_number': account_number},
            ttl=0
        )
        if not account_name_and_provider.empty:
            return account_name_and_provider.iloc[0][account_number_col], account_name_and_provider.iloc[0][provider_col]
        return None, None

    def add_rule(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                 method: Literal['All', 'From now on'], account_number: str | None = None) -> None:
        """
        Add a new automatic tagging rule to the database.

        Creates a new rule in the auto tagger table and optionally updates existing
        transactions based on the specified method.

        Parameters
        ----------
        name : str
            The name/description of the transaction.
        category : str
            The category to assign.
        tag : str
            The tag to assign.
        service : Literal['credit_card', 'bank']
            The service type ('credit_card' or 'bank').
        method : Literal['All', 'From now on']
            The update method:
            - 'All': Update all existing transactions matching the rule
            - 'From now on': Only apply the rule to new transactions
        account_number : str | None, optional
            The account number for bank transactions (required for bank, optional for credit card).

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If an invalid update method is provided.
        """
        self.auto_tagger_repo.add_to_table(name, category, tag, service, account_number)

        if method == 'All':
            self.transactions_service.update_tagging(name, category, tag, service, account_number)
        elif method == 'From now on':
            pass  # do nothing
        else:
            raise ValueError(f"Invalid auto tagger update method: {method}")

    def update_rule(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                    method: Literal['All', 'From now on'], account_number: str | None = None) -> None:
        """
        Update an existing auto tagger rule in the database.

        Parameters
        ----------
        name : str
            The name/description of the transaction.
        category : str
            The category to assign.
        tag : str
            The tag to assign.
        service : Literal['credit_card', 'bank']
            The service type ('credit_card' or 'bank').
        method : Literal['All', 'From now on']
            The update method ('All' or 'From now on').
        account_number : str | None
            The account number for bank transactions (optional for credit card).

        Returns
        -------
        None
        """
        self.auto_tagger_repo.update_table(name, category, tag, service, account_number)

        if method == 'All':
            self.transactions_service.update_tagging(name, category, tag, service, account_number)
        elif method == 'From now on':
            pass  # No additional action needed
        else:
            raise ValueError(f"Invalid update method: {method}")

    def update_raw_data_by_rules(self) -> None:
        """
        Apply automatic tagging rules to all untagged raw transaction data.

        This method applies the rules from the auto tagger table to both credit card
        and bank transactions that don't have tags yet.
        """
        self.auto_tagger_repo.update_raw_data_by_rules('credit_card')
        self.auto_tagger_repo.update_raw_data_by_rules('bank')
