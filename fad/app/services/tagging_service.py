from typing import Dict, List, Tuple
import streamlit as st
from fad.app.data_access.tagging_data import load_categories_and_tags, save_categories_and_tags
from fad.app.utils.data import get_categories_and_tags, format_category_or_tag_strings, assure_tags_table, get_table
from streamlit.connections import SQLConnection
from sqlalchemy import text
from typing import Literal
from fad.app.data_access.tagging_repository import AutoTaggerRepository
from fad.app.data_access.transactions_repository import TransactionsRepository

from fad.app.naming_conventions import (
    Tables,
    AutoTaggerTableFields,
    CreditCardTableFields,
    BankTableFields,
)

tags_table = Tables.AUTO_TAGGER.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
category_col = AutoTaggerTableFields.CATEGORY.value
tag_col = AutoTaggerTableFields.TAG.value
name_col = AutoTaggerTableFields.NAME.value
service_col = AutoTaggerTableFields.SERVICE.value
account_number_col = AutoTaggerTableFields.ACCOUNT_NUMBER.value



def _sorted_unique(lst):
    return sorted(list(set(lst)))

class CategoriesTagsService:
    def __init__(self):
        if 'categories_and_tags' not in st.session_state:
            st.session_state['categories_and_tags'] = load_categories_and_tags()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def add_category(self, category: str) -> bool:
        if not category or not isinstance(category, str) or not category.strip():
            return False
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.categories_and_tags[category] = []
        self._save()
        return True

    def delete_category(self, category: str, protected_categories: List[str]) -> bool:
        # TODO: delete category from db data
        if category in protected_categories:
            return False
        if category in self.categories_and_tags:
            del self.categories_and_tags[category]
            self._save()
            return True
        return False

    def reallocate_tags(self, old_category: str, new_category: str, tags: List[str]) -> bool:
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
        if category not in self.categories_and_tags:
            return False
        if tag in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].append(tag)
        self._save()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        # TODO: delete tag from db data

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].remove(tag)
        self._save()
        return True

    def _save(self):
        st.session_state['categories_and_tags'] = self.categories_and_tags
        save_categories_and_tags(self.categories_and_tags)


class AutomaticTaggerService:
    def __init__(self, conn: SQLConnection):
        """
        Initialize the CategoriesAndTags object

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database
        """
        self.conn = conn
        self.auto_tagger_repo = AutoTaggerRepository(conn)
        self.transactions_repo = TransactionsRepository(conn)

    def get_cc_without_rules(self) -> List[str]:
        """
        Get credit card transactions that do not have rules associated with them

        Returns
        -------
        List[Dict[str, str]]
            A list of dictionaries containing credit card transactions without rules
        """
        # get all credit card transactions that do not apear in the auto tagger rules table
        auto_tagger_table = get_table(self.conn, Tables.AUTO_TAGGER.value)
        cc_table = get_table(self.conn, Tables.CREDIT_CARD.value)

        desc_col = self.transactions_repo.desc_col
        cc_without_rules = cc_table.loc[~cc_table[desc_col].isin(auto_tagger_table[name_col]), desc_col].unique().tolist()

        return cc_without_rules

    def get_bank_without_rules(self) -> List[Tuple[str, str]]:
        """
        Get bank transactions that do not have rules associated with them

        Returns
        -------
        List[(str, str)]
            A list of tuples containing bank transactions without rules, where each tuple is (description, account_number)
        """
        auto_tagger_table = get_table(self.conn, Tables.AUTO_TAGGER.value)
        bank_table = get_table(self.conn, Tables.BANK.value)

        desc_col = self.transactions_repo.desc_col
        bank_account_number_col = self.transactions_repo.account_number_col
        name_col = self.auto_tagger_repo.name_col
        auto_tagger_account_number_col = self.auto_tagger_repo.account_number_col

        bank_ids = bank_table[[desc_col, bank_account_number_col]].drop_duplicates()
        auto_ids = auto_tagger_table[[name_col, auto_tagger_account_number_col]].drop_duplicates()

        bank_set: set[Tuple[str, str]] = set(map(tuple, bank_ids.values))  # noqa
        auto_set: set[Tuple[str, str]] = set(map(tuple, auto_ids.values))  # noqa

        result = sorted(bank_set - auto_set)
        return result

    def get_bank_account_details(self, account_number: str) -> (str, str):
        provider_col = self.transactions_repo.provider_col
        account_number_col = self.transactions_repo.account_number_col

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
        """update the auto tagger rules in the database"""
        self.auto_tagger_repo.add_to_table(name, category, tag, service, account_number)

        if method == 'All':
            self.transactions_repo.update_tagging(name, category, tag, service, account_number)
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
            self.transactions_repo.update_tagging(name, category, tag, service, account_number)
        elif method == 'From now on':
            pass  # No additional action needed
        else:
            raise ValueError(f"Invalid update method: {method}")

