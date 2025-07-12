import os
from typing import Dict, List
from typing import Literal, Optional

import pandas as pd
import sqlalchemy as sa
import yaml
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import (
    Tables,
    AutoTaggerTableFields,
    TransactionsTableFields,
)


class TaggingRepository:
    """
    Repository for basic CRUD operations on tagging data.
    Contains only data access logic, no business logic.
    """

    @staticmethod
    def load_categories_from_file(file_path: str) -> dict[str, list[str]]:
        """Load categories and tags from a YAML file."""
        with open(file_path, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader)

    @staticmethod
    def save_categories_to_file(categories_and_tags: Dict[str, List[str]], file_path: str) -> None:
        """Save categories and tags to a YAML file."""
        with open(file_path, 'w') as file:
            yaml.dump(categories_and_tags, file)

    @staticmethod
    def file_exists(file_path: str) -> bool:
        """Check if a file exists."""
        return os.path.exists(file_path)

    @staticmethod
    def create_directory(dir_path: str) -> None:
        """Create directory if it doesn't exist."""
        os.makedirs(dir_path, exist_ok=True)


class AutoTaggerRepository:
    """
    Repository for basic CRUD operations on auto tagger data.
    Contains only data access logic, no business logic.
    """
    table = Tables.AUTO_TAGGER.value
    category_col = AutoTaggerTableFields.CATEGORY.value
    tag_col = AutoTaggerTableFields.TAG.value
    name_col = AutoTaggerTableFields.NAME.value
    service_col = AutoTaggerTableFields.SERVICE.value
    account_number_col = AutoTaggerTableFields.ACCOUNT_NUMBER.value
    id_col = AutoTaggerTableFields.ID.value

    def __init__(self, conn: SQLConnection):
        self.conn = conn
        self.assure_table_exists()

    def assure_table_exists(self):
        """create the tags table if it doesn't exist"""
        with self.conn.session as s:
            s.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS {self.table} ('
                    f'id INTEGER PRIMARY KEY AUTOINCREMENT, '
                    f'{self.name_col} TEXT, '
                    f'{self.category_col} TEXT, '
                    f'{self.tag_col} TEXT, '
                    f'{self.service_col} TEXT, '
                    f'{self.account_number_col} TEXT'
                    f');'
                )
            )
            s.commit()

    def get_table(self, service: Literal['credit_card', 'bank'] | None = None) -> pd.DataFrame:
        """Get the auto tagger table as a DataFrame"""
        if service:
            query = f'SELECT * FROM {self.table} WHERE {self.service_col} = :service;'
            params = {'service': service}
        else:
            query = f'SELECT * FROM {self.table};'
            params = {}

        table = self.conn.query(query, params=params, ttl=0)
        return table

    def add_to_table(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                     account_number: Optional[str] = None) -> int:
        """Add a new auto tagger rule to the database. Returns the new row id."""
        if service == "bank" and account_number is None:
            raise ValueError("account_number is required for bank transactions")

        # Optionally check for duplicates (by name, service, account_number)
        with self.conn.session as s:
            check_query = sa.text(f"""
                SELECT id FROM {self.table}
                WHERE {self.name_col} = :name AND {self.service_col} = :service AND {self.account_number_col} IS :account_number
            """)
            result = s.execute(check_query, {'name': name, 'service': service, 'account_number': account_number})
            row = result.fetchone()
            if row:
                return row[0]  # Return existing id

            params = {
                'name': name,
                'category': category,
                'tag': tag,
                'service': service,
                'account_number': account_number
            }
            query = sa.text(f"""
                INSERT INTO {self.table} ({self.name_col}, {self.category_col}, {self.tag_col}, {self.service_col}, {self.account_number_col})
                VALUES (:name, :category, :tag, :service, :account_number)
            """)
            result = s.execute(query, params)
            s.commit()
            return result.lastrowid

    def update_by_id(self, id_: int, category: str, tag: str) -> None:
        """Update auto tagger rule by id."""
        with self.conn.session as s:
            params = {'id': id_, 'category': category, 'tag': tag}
            query = sa.text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :category, {self.tag_col} = :tag
                WHERE id = :id
            """)
            s.execute(query, params)
            s.commit()

    def delete_by_id(self, id_: int) -> None:
        """Delete auto tagger rule by id."""
        with self.conn.session as s:
            query = sa.text(f"DELETE FROM {self.table} WHERE id = :id")
            s.execute(query, {'id': id_})
            s.commit()

    def update_table(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                     account_number: Optional[str] = None) -> None:
        """Update auto tagger rule in the database (legacy, not id-based)."""
        if service == "bank" and account_number is None:
            raise ValueError("account_number is required for bank transactions")

        with self.conn.session as s:
            params = {
                'name': name,
                'category': category,
                'tag': tag,
                'service': service,
                'account_number': account_number
            }

            query = sa.text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :category,
                    {self.tag_col} = :tag
                WHERE {self.name_col} = :name
                AND {self.service_col} = :service
                AND {self.account_number_col} IS :account_number
            """)

            s.execute(query, params)
            s.commit()

    def delete_by_category_and_tag(self, category: str, tag: str) -> None:
        """
        Delete auto tagger rules with the specified category and tag (optionally filtered by service and account_number).
        """
        with self.conn.session as s:
            query = sa.text(f"""
                DELETE FROM {self.table}
                WHERE {self.category_col} = :category AND {self.tag_col} = :tag
            """)
            params = {'category': category, 'tag': tag}
            s.execute(query, params)
            s.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """
        Update the category to new_category for all auto tagger rules with the specified old_category and tag.
        """
        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :new_category
                WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
            """)
            params = {'new_category': new_category, 'old_category': old_category, 'tag': tag}
            s.execute(query, params)
            s.commit()

    def delete_by_category(self, category: str) -> None:
        """
        Delete all auto tagger rules with the specified category.
        """
        with self.conn.session as s:
            query = sa.text(f"""
                DELETE FROM {self.table}
                WHERE {self.category_col} = :category
            """)
            params = {'category': category}
            s.execute(query, params)
            s.commit()

    def update_credit_card_transactions_by_rules(self) -> None:
        """Update credit card raw data based on auto tagger rules - Pure SQL operation"""
        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {Tables.CREDIT_CARD.value}
                SET {TransactionsTableFields.CATEGORY.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.CATEGORY.value},
                    {TransactionsTableFields.TAG.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.TAG.value}
                FROM {Tables.AUTO_TAGGER.value}
                WHERE {Tables.CREDIT_CARD.value}.{TransactionsTableFields.DESCRIPTION.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.NAME.value}
                AND {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.SERVICE.value} = 'credit_card'
                AND {Tables.CREDIT_CARD.value}.{TransactionsTableFields.CATEGORY.value} IS NULL
            """)
            s.execute(query)
            s.commit()

    def update_bank_transactions_by_rules(self) -> None:
        """Update bank raw data based on auto tagger rules - Pure SQL operation"""
        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {Tables.BANK.value}
                SET {TransactionsTableFields.CATEGORY.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.CATEGORY.value},
                    {TransactionsTableFields.TAG.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.TAG.value}
                FROM {Tables.AUTO_TAGGER.value}
                WHERE {Tables.BANK.value}.{TransactionsTableFields.DESCRIPTION.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.NAME.value}
                AND {Tables.BANK.value}.{TransactionsTableFields.ACCOUNT_NUMBER.value} = {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.ACCOUNT_NUMBER.value}
                AND {Tables.AUTO_TAGGER.value}.{AutoTaggerTableFields.SERVICE.value} = 'bank'
                AND {Tables.BANK.value}.{TransactionsTableFields.CATEGORY.value} IS NULL
            """)
            s.execute(query)
            s.commit()
