import sqlalchemy as sa
import pandas as pd
from typing import Literal, Optional
from streamlit.connections import SQLConnection
from sqlalchemy.sql import text

from fad.app.naming_conventions import (
    Tables,
    AutoTaggerTableFields,
    TransactionsTableFields,
)


class AutoTaggerRepository:
    table = Tables.AUTO_TAGGER.value
    category_col = AutoTaggerTableFields.CATEGORY.value
    tag_col = AutoTaggerTableFields.TAG.value
    name_col = AutoTaggerTableFields.NAME.value
    service_col = AutoTaggerTableFields.SERVICE.value
    account_number_col = AutoTaggerTableFields.ACCOUNT_NUMBER.value

    def __init__(self, conn: SQLConnection):
        self.conn = conn
        self.assure_table_exists()

    def assure_table_exists(self):
        """create the tags table if it doesn't exist"""
        with self.conn.session as s:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {self.table} ({self.name_col} TEXT PRIMARY KEY, {self.category_col}'
                     f' TEXT, {self.tag_col} TEXT, {self.service_col} TEXT, {self.account_number_col} TEXT);'))
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
                     account_number: Optional[str] = None) -> None:
        """Add a new auto tagger rule to the database"""
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
                INSERT INTO {Tables.AUTO_TAGGER.value} ({AutoTaggerTableFields.NAME.value}, 
                    {AutoTaggerTableFields.CATEGORY.value}, {AutoTaggerTableFields.TAG.value}, 
                    {AutoTaggerTableFields.SERVICE.value}, {AutoTaggerTableFields.ACCOUNT_NUMBER.value})
                VALUES (:name, :category, :tag, :service, :account_number)
                ON CONFLICT ({AutoTaggerTableFields.NAME.value}, {AutoTaggerTableFields.SERVICE.value}) 
                DO UPDATE SET {AutoTaggerTableFields.CATEGORY.value} = :category, 
                              {AutoTaggerTableFields.TAG.value} = :tag,
                              {AutoTaggerTableFields.ACCOUNT_NUMBER.value} = :account_number
            """)

            s.execute(query, params)
            s.commit()

    def update_table(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                     account_number: Optional[str] = None) -> None:
        """Update auto tagger rule in the database"""
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
                UPDATE {Tables.AUTO_TAGGER.value}
                SET {AutoTaggerTableFields.CATEGORY.value} = :category,
                    {AutoTaggerTableFields.TAG.value} = :tag
                WHERE {AutoTaggerTableFields.NAME.value} = :name
                AND {AutoTaggerTableFields.SERVICE.value} = :service
                AND {AutoTaggerTableFields.ACCOUNT_NUMBER.value} = :account_number
            """)

            s.execute(query, params)
            s.commit()

    def update_raw_data_by_rules(self, service: Literal['credit_card', 'bank']) -> None:
        """Update raw data based on auto tagger rules"""
        if service == 'credit_card':
            self._update_raw_data_by_rules_credit_card()
        else:
            self._update_raw_data_by_rules_bank()

    def _update_raw_data_by_rules_credit_card(self) -> None:
        """Update credit card raw data based on auto tagger rules"""
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

    def _update_raw_data_by_rules_bank(self) -> None:
        """Update bank raw data based on auto tagger rules"""
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
