import sqlalchemy as sa
import pandas as pd
from typing import Literal, Optional
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import (
    Tables,
    TagsTableFields,
    CreditCardTableFields,
    BankTableFields,
    Services
)

class TaggingRepository:
    def __init__(self, conn: SQLConnection):
        self.conn = conn

class CategoriesAndTagsRepository(TaggingRepository):
    def get_categories_and_tags(self) -> dict[str, list[str]]:
        """Get all categories and their tags from the database"""
        with self.conn.session as s:
            query = sa.text(f"SELECT DISTINCT {TagsTableFields.CATEGORY.value}, {TagsTableFields.TAG.value} FROM {Tables.TAGS.value}")
            result = s.execute(query).mappings()
            categories_and_tags = {}
            for row in result:
                category = row[TagsTableFields.CATEGORY.value]
                tag = row[TagsTableFields.TAG.value]
                if category not in categories_and_tags:
                    categories_and_tags[category] = []
                if tag not in categories_and_tags[category]:
                    categories_and_tags[category].append(tag)
            return categories_and_tags

    def update_category_and_tag(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'], 
                              account_number: Optional[str] = None) -> None:
        """Update category and tag for a transaction"""
        with self.conn.session as s:
            params = {
                'name': name,
                'category': category,
                'tag': tag,
                'service': service
            }
            
            if service == 'credit_card':
                query = sa.text(f"""
                    UPDATE {Tables.CREDIT_CARD.value}
                    SET {CreditCardTableFields.CATEGORY.value} = :category,
                        {CreditCardTableFields.TAG.value} = :tag
                    WHERE {CreditCardTableFields.DESCRIPTION.value} = :name
                """)
            else:  # bank
                if account_number is None:
                    raise ValueError("account_number is required for bank transactions")
                query = sa.text(f"""
                    UPDATE {Tables.BANK.value}
                    SET {BankTableFields.CATEGORY.value} = :category,
                        {BankTableFields.TAG.value} = :tag
                    WHERE {BankTableFields.DESCRIPTION.value} = :name
                    AND {BankTableFields.ACCOUNT_NUMBER.value} = :account_number
                """)
                params['account_number'] = account_number
            
            s.execute(query, params)
            s.commit()

    def pull_new_transaction_names(self, service: Literal['credit_card', 'bank']) -> None:
        """Pull new transaction names from credit card or bank tables"""
        if service == 'credit_card':
            self._pull_new_cc_names()
        else:
            self._pull_new_bank_names()

    def _pull_new_cc_names(self) -> None:
        """Pull new credit card transaction names"""
        with self.conn.session as s:
            # Get existing names from tags table
            existing_names = s.execute(sa.text(f"""
                SELECT {TagsTableFields.NAME.value}
                FROM {Tables.TAGS.value}
                WHERE {TagsTableFields.SERVICE.value} = 'credit_card'
            """)).fetchall()
            existing_names = [row[0] for row in existing_names]

            # Get new names from credit card table
            new_names = s.execute(sa.text(f"""
                SELECT DISTINCT {CreditCardTableFields.DESCRIPTION.value}
                FROM {Tables.CREDIT_CARD.value}
                WHERE {CreditCardTableFields.DESCRIPTION.value} NOT IN :existing_names
            """), {'existing_names': tuple(existing_names) if existing_names else ('',)}).fetchall()

            # Insert new names into tags table
            for name in new_names:
                s.execute(sa.text(f"""
                    INSERT INTO {Tables.TAGS.value}
                    ({TagsTableFields.NAME.value}, {TagsTableFields.SERVICE.value})
                    VALUES (:name, 'credit_card')
                """), {'name': name[0]})
            s.commit()

    def _pull_new_bank_names(self) -> None:
        """Pull new bank transaction names"""
        with self.conn.session as s:
            # Get existing names and account numbers from tags table
            existing = s.execute(sa.text(f"""
                SELECT {TagsTableFields.NAME.value}, {TagsTableFields.ACCOUNT_NUMBER.value}
                FROM {Tables.TAGS.value}
                WHERE {TagsTableFields.SERVICE.value} = 'bank'
            """)).fetchall()
            existing = {(row[0], row[1]) for row in existing}

            # Get new names and account numbers from bank table
            new_transactions = s.execute(sa.text(f"""
                SELECT DISTINCT {BankTableFields.DESCRIPTION.value}, {BankTableFields.ACCOUNT_NUMBER.value}
                FROM {Tables.BANK.value}
            """)).fetchall()

            # Insert new names into tags table
            for name, account_number in new_transactions:
                if (name, account_number) not in existing:
                    s.execute(sa.text(f"""
                        INSERT INTO {Tables.TAGS.value}
                        ({TagsTableFields.NAME.value}, {TagsTableFields.ACCOUNT_NUMBER.value}, {TagsTableFields.SERVICE.value})
                        VALUES (:name, :account_number, 'bank')
                    """), {'name': name, 'account_number': account_number})
            s.commit()

class AutoTaggerRepository(TaggingRepository):
    def get_untagged_transactions(self, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """Get all untagged transactions for a service"""
        if service == 'credit_card':
            table = Tables.CREDIT_CARD.value
            desc_col = CreditCardTableFields.DESCRIPTION.value
            category_col = CreditCardTableFields.CATEGORY.value
        else:  # bank
            table = Tables.BANK.value
            desc_col = BankTableFields.DESCRIPTION.value
            category_col = BankTableFields.CATEGORY.value

        with self.conn.session as s:
            query = sa.text(f"""
                SELECT DISTINCT {desc_col}
                FROM {table}
                WHERE {category_col} IS NULL
            """)
            result = s.execute(query)
            return pd.DataFrame(result.fetchall(), columns=[desc_col])

    def update_auto_tagger_rule(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                              account_number: Optional[str] = None) -> None:
        """Update auto tagger rule in the database"""
        with self.conn.session as s:
            params = {
                'name': name,
                'category': category,
                'tag': tag,
                'service': service
            }
            
            if service == 'credit_card':
                query = sa.text(f"""
                    UPDATE {Tables.TAGS.value}
                    SET {TagsTableFields.CATEGORY.value} = :category,
                        {TagsTableFields.TAG.value} = :tag
                    WHERE {TagsTableFields.NAME.value} = :name
                    AND {TagsTableFields.SERVICE.value} = :service
                """)
            else:  # bank
                if account_number is None:
                    raise ValueError("account_number is required for bank transactions")
                query = sa.text(f"""
                    UPDATE {Tables.TAGS.value}
                    SET {TagsTableFields.CATEGORY.value} = :category,
                        {TagsTableFields.TAG.value} = :tag
                    WHERE {TagsTableFields.NAME.value} = :name
                    AND {TagsTableFields.SERVICE.value} = :service
                    AND {TagsTableFields.ACCOUNT_NUMBER.value} = :account_number
                """)
                params['account_number'] = account_number
            
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
                SET {CreditCardTableFields.CATEGORY.value} = {Tables.TAGS.value}.{TagsTableFields.CATEGORY.value},
                    {CreditCardTableFields.TAG.value} = {Tables.TAGS.value}.{TagsTableFields.TAG.value}
                FROM {Tables.TAGS.value}
                WHERE {Tables.CREDIT_CARD.value}.{CreditCardTableFields.DESCRIPTION.value} = {Tables.TAGS.value}.{TagsTableFields.NAME.value}
                AND {Tables.TAGS.value}.{TagsTableFields.SERVICE.value} = 'credit_card'
                AND {Tables.CREDIT_CARD.value}.{CreditCardTableFields.CATEGORY.value} IS NULL
            """)
            s.execute(query)
            s.commit()

    def _update_raw_data_by_rules_bank(self) -> None:
        """Update bank raw data based on auto tagger rules"""
        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {Tables.BANK.value}
                SET {BankTableFields.CATEGORY.value} = {Tables.TAGS.value}.{TagsTableFields.CATEGORY.value},
                    {BankTableFields.TAG.value} = {Tables.TAGS.value}.{TagsTableFields.TAG.value}
                FROM {Tables.TAGS.value}
                WHERE {Tables.BANK.value}.{BankTableFields.DESCRIPTION.value} = {Tables.TAGS.value}.{TagsTableFields.NAME.value}
                AND {Tables.BANK.value}.{BankTableFields.ACCOUNT_NUMBER.value} = {Tables.TAGS.value}.{TagsTableFields.ACCOUNT_NUMBER.value}
                AND {Tables.TAGS.value}.{TagsTableFields.SERVICE.value} = 'bank'
                AND {Tables.BANK.value}.{BankTableFields.CATEGORY.value} IS NULL
            """)
            s.execute(query)
            s.commit()

class ManualTaggerRepository(TaggingRepository):
    def get_transaction_by_id(self, service: Literal['credit_card', 'bank'], id_: int) -> pd.Series:
        """Get a transaction by its ID"""
        if service == 'credit_card':
            table = Tables.CREDIT_CARD.value
            id_col = CreditCardTableFields.ID.value
        else:  # bank
            table = Tables.BANK.value
            id_col = BankTableFields.ID.value

        with self.conn.session as s:
            query = sa.text(f"SELECT * FROM {table} WHERE {id_col} = :id")
            result = s.execute(query, {'id': id_})
            return pd.Series(result.fetchone())

    def update_transaction_tags(self, service: Literal['credit_card', 'bank'], id_: int, 
                              category: str, tag: str) -> None:
        """Update tags for a specific transaction"""
        if service == 'credit_card':
            table = Tables.CREDIT_CARD.value
            id_col = CreditCardTableFields.ID.value
            category_col = CreditCardTableFields.CATEGORY.value
            tag_col = CreditCardTableFields.TAG.value
        else:  # bank
            table = Tables.BANK.value
            id_col = BankTableFields.ID.value
            category_col = BankTableFields.CATEGORY.value
            tag_col = BankTableFields.TAG.value

        with self.conn.session as s:
            query = sa.text(f"""
                UPDATE {table}
                SET {category_col} = :category,
                    {tag_col} = :tag
                WHERE {id_col} = :id
            """)
            s.execute(query, {'id': id_, 'category': category, 'tag': tag})
            s.commit()

    def get_filtered_transactions(self, service: Literal['credit_card', 'bank'], 
                                filters: dict) -> pd.DataFrame:
        """Get transactions filtered by various criteria"""
        if service == 'credit_card':
            table = Tables.CREDIT_CARD.value
            fields = CreditCardTableFields
        else:  # bank
            table = Tables.BANK.value
            fields = BankTableFields

        with self.conn.session as s:
            query = sa.text(f"SELECT * FROM {table}")
            result = s.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            
            # Apply filters
            for field, value in filters.items():
                if value is not None:
                    if isinstance(value, list):
                        df = df[df[field].isin(value)]
                    elif isinstance(value, tuple):
                        df = df[(df[field] >= value[0]) & (df[field] <= value[1])]
                    else:
                        df = df[df[field] == value]
            
            return df 