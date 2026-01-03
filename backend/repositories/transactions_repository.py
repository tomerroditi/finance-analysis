"""
Transactions repository with pure SQLAlchemy (no Streamlit dependencies).

This module provides data access for transaction-related operations.
"""
from datetime import datetime
from typing import Literal, Optional
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.repositories.split_transactions_repository import SplitTransactionsRepository

# Import naming conventions from the original location
# These don't have Streamlit dependencies
from fad.app.naming_conventions import (
    Tables, CreditCardTableFields, BankTableFields, CashTableFields, 
    TransactionsTableFields, Services, ManualInvestmentTransactionsTableFields
)


DEPOSIT_TYPE = 'deposit'
WITHDRAWAL_TYPE = 'withdrawal'


@dataclass
class CashTransaction:
    """Data class representing a cash transaction."""
    date: datetime
    account_name: str
    desc: str
    amount: float
    provider: str | None = None
    account_number: str | None = None
    category: str | None = None
    tag: str | None = None


@dataclass
class ManualInvestmentTransaction:
    """Data class representing a manual investment transaction."""
    date: datetime
    account_name: str
    desc: str
    amount: float
    transaction_type: Literal['deposit', 'withdrawal']
    provider: str
    account_number: str
    category: str
    tag: str


T_service = Literal[
    'credit_card', 'bank', 'cash', 'manual_investments',
    'credit_card_transactions', 'bank_transactions', 'cash_transactions', 
    'manual_investment_transactions'
]


class ServiceRepository:
    """
    Base class for service-specific transaction repositories.
    
    Provides common CRUD operations for transaction data using pure SQLAlchemy.
    """
    table: str
    unique_id_col = 'unique_id'
    account_number_col = TransactionsTableFields.ACCOUNT_NUMBER.value
    type_col = TransactionsTableFields.TYPE.value
    id_col = TransactionsTableFields.ID.value
    date_col = TransactionsTableFields.DATE.value
    desc_col = TransactionsTableFields.DESCRIPTION.value
    amount_col = TransactionsTableFields.AMOUNT.value
    status_col = TransactionsTableFields.STATUS.value
    account_name_col = TransactionsTableFields.ACCOUNT_NAME.value
    provider_col = TransactionsTableFields.PROVIDER.value
    category_col = TransactionsTableFields.CATEGORY.value
    tag_col = TransactionsTableFields.TAG.value
    source_col = TransactionsTableFields.SOURCE.value

    unique_columns = [id_col, provider_col, date_col, amount_col]

    col_type_mapping = {
        'unique_id': "INTEGER PRIMARY KEY AUTOINCREMENT",
        'id': "TEXT",
        'date': "TEXT",
        'provider': "TEXT",
        'account_name': "TEXT",
        'account_number': "TEXT",
        'desc': "TEXT",
        'amount': "REAL",
        'category': "TEXT DEFAULT NULL",
        'tag': "TEXT DEFAULT NULL",
        'source': "TEXT",
        'type': "TEXT DEFAULT 'normal'",
        'status': "TEXT DEFAULT 'completed'"
    }

    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._assure_table_exists()

    def _assure_table_exists(self) -> None:
        """Ensure that the transactions table exists in the database."""
        my_query = f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                {self.unique_id_col} {self.col_type_mapping[self.unique_id_col]},
                {self.id_col} {self.col_type_mapping[self.id_col]},
                {self.date_col} {self.col_type_mapping[self.date_col]},
                {self.provider_col} {self.col_type_mapping[self.provider_col]},
                {self.account_name_col} {self.col_type_mapping[self.account_name_col]},
                {self.account_number_col} {self.col_type_mapping[self.account_number_col]},
                {self.desc_col} {self.col_type_mapping[self.desc_col]},
                {self.amount_col} {self.col_type_mapping[self.amount_col]},
                {self.category_col} {self.col_type_mapping[self.category_col]},
                {self.tag_col} {self.col_type_mapping[self.tag_col]},
                {self.source_col} {self.col_type_mapping[self.source_col]},
                {self.type_col} {self.col_type_mapping[self.type_col]},
                {self.status_col} {self.col_type_mapping[self.status_col]},
                UNIQUE ({', '.join(self.unique_columns)})
            )
        """
        self.db.execute(text(my_query))
        self.db.commit()

    def get_table(self, query: str | None = None, params: dict | None = None) -> pd.DataFrame:
        """
        Get the transactions table as a DataFrame.

        Parameters
        ----------
        query : str, optional
            Custom SQL query to execute.
        params : dict, optional
            Parameters for the SQL query.

        Returns
        -------
        pd.DataFrame
            The transactions data.
        """
        if query:
            result = self.db.execute(text(query), params or {})
            columns = result.keys()
            data = result.fetchall()
            return pd.DataFrame(data, columns=columns)
        else:
            result = self.db.execute(text(f"SELECT *, '{self.table}' as {self.source_col} FROM {self.table}"))
            columns = result.keys()
            data = result.fetchall()
            return pd.DataFrame(data, columns=columns)

    def update_with_query(self, query: str, query_params: dict | None = None) -> int:
        """
        Execute an UPDATE query and return the number of affected rows.

        Parameters
        ----------
        query : str
            SQL UPDATE query.
        query_params : dict, optional
            Parameters for the query.

        Returns
        -------
        int
            Number of rows updated.
        """
        if not query.strip().lower().startswith('update'):
            raise ValueError("The query must be an UPDATE statement.")

        result = self.db.execute(text(query), query_params or {})
        self.db.commit()
        return result.rowcount

    def get_table_columns(self) -> list[str]:
        """Get the column names for display purposes."""
        return [
            self.id_col,
            self.date_col,
            self.provider_col,
            self.account_name_col,
            self.account_number_col,
            self.desc_col,
            self.amount_col,
            self.category_col,
            self.tag_col
        ]

    def update_tagging_by_id(self, id_: str, category: str, tag: str) -> None:
        """Update category and tag for a transaction by ID."""
        my_query = f"""
            UPDATE {self.table}
            SET {self.category_col} = :category_val, {self.tag_col} = :tag_val
            WHERE {self.id_col} = :id_val
        """
        params = {
            'category_val': category,
            'tag_val': tag,
            'id_val': id_
        }
        self.db.execute(text(my_query), params)
        self.db.commit()

    def delete_transaction_by_id(self, transaction_id: str) -> bool:
        """Delete a transaction by its unique_id."""
        my_query = f"""
            DELETE FROM {self.table}
            WHERE {self.unique_id_col} = :id_val
        """
        try:
            result = self.db.execute(text(my_query), {'id_val': int(transaction_id)})
            self.db.commit()
            return result.rowcount > 0
        except Exception:
            self.db.rollback()
            return False

    def update_transaction_by_id(self, transaction_id: str, updates: dict) -> bool:
        """Update a transaction by its unique_id."""
        if not updates:
            return True
        
        set_clause = ", ".join([f"{col} = :{col}" for col in updates.keys()])
        my_query = f"""
            UPDATE {self.table}
            SET {set_clause}
            WHERE {self.unique_id_col} = :id_val
        """
        params = {**updates, 'id_val': int(transaction_id)}
        try:
            result = self.db.execute(text(my_query), params)
            self.db.commit()
            return result.rowcount > 0
        except Exception:
            self.db.rollback()
            return False
    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for all transactions with the specified category."""
        my_query = f"""
            UPDATE {self.table}
            SET {self.category_col} = NULL, {self.tag_col} = NULL
            WHERE {self.category_col} = :category_val
        """
        self.db.execute(text(my_query), {'category_val': category})
        self.db.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """Update category for all transactions with specified old_category and tag."""
        my_query = f"""
            UPDATE {self.table}
            SET {self.category_col} = :new_category
            WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
        """
        params = {
            'new_category': new_category,
            'old_category': old_category,
            'tag': tag
        }
        self.db.execute(text(my_query), params)
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for transactions with specified category and tag."""
        my_query = f"""
            UPDATE {self.table}
            SET {self.category_col} = NULL, {self.tag_col} = NULL
            WHERE {self.category_col} = :category_val AND {self.tag_col} = :tag_val
        """
        params = {
            'category_val': category,
            'tag_val': tag
        }
        self.db.execute(text(my_query), params)
        self.db.commit()

    def add_transaction(self, transaction: CashTransaction | ManualInvestmentTransaction) -> bool:
        """Add a new transaction to the database."""
        my_query = f"""
            INSERT INTO {self.table} (
                {self.date_col},
                {self.provider_col},
                {self.account_name_col},
                {self.account_number_col},
                {self.desc_col},
                {self.amount_col},
                {self.category_col},
                {self.tag_col},
                {self.id_col}
            ) VALUES (
                :date_val,
                :provider_val,
                :account_name_val,
                :account_number_val,
                :desc_val,
                :amount_val,
                :category_val,
                :tag_val,
                :id_val
            )
        """
        params = {
            'date_val': transaction.date.strftime('%Y-%m-%d'),
            'provider_val': transaction.provider,
            'account_name_val': transaction.account_name,
            'account_number_val': transaction.account_number,
            'desc_val': transaction.desc,
            'amount_val': transaction.amount,
            'category_val': transaction.category,
            'tag_val': transaction.tag
        }
        try:
            # Get max ID for this table
            max_id = self.db.execute(
                text(f'SELECT MAX({self.id_col}) FROM {self.table}')
            ).scalar()
            params['id_val'] = (int(max_id) + 1) if max_id is not None else 1
            self.db.execute(text(my_query), params)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False


class CreditCardRepository(ServiceRepository):
    """Repository for credit card transactions."""
    table = Tables.CREDIT_CARD.value
    desc_col = CreditCardTableFields.DESCRIPTION.value
    tag_col = CreditCardTableFields.TAG.value
    category_col = CreditCardTableFields.CATEGORY.value
    id_col = CreditCardTableFields.ID.value
    date_col = CreditCardTableFields.DATE.value
    provider_col = CreditCardTableFields.PROVIDER.value
    account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
    account_number_col = CreditCardTableFields.ACCOUNT_NUMBER.value
    amount_col = CreditCardTableFields.AMOUNT.value
    type_col = CreditCardTableFields.TYPE.value
    status_col = CreditCardTableFields.STATUS.value


class BankRepository(ServiceRepository):
    """Repository for bank transactions."""
    table = Tables.BANK.value
    desc_col = BankTableFields.DESCRIPTION.value
    tag_col = BankTableFields.TAG.value
    category_col = BankTableFields.CATEGORY.value
    id_col = BankTableFields.ID.value
    account_number_col = BankTableFields.ACCOUNT_NUMBER.value
    date_col = BankTableFields.DATE.value
    provider_col = BankTableFields.PROVIDER.value
    account_name_col = BankTableFields.ACCOUNT_NAME.value
    amount_col = BankTableFields.AMOUNT.value
    type_col = BankTableFields.TYPE.value
    status_col = BankTableFields.STATUS.value


class CashRepository(ServiceRepository):
    """Repository for cash transactions."""
    table = Tables.CASH.value
    desc_col = CashTableFields.DESCRIPTION.value
    tag_col = CashTableFields.TAG.value
    category_col = CashTableFields.CATEGORY.value
    id_col = CashTableFields.ID.value
    account_number_col = CashTableFields.ACCOUNT_NUMBER.value
    date_col = CashTableFields.DATE.value
    provider_col = CashTableFields.PROVIDER.value
    account_name_col = CashTableFields.ACCOUNT_NAME.value
    amount_col = CashTableFields.AMOUNT.value
    type_col = CashTableFields.TYPE.value
    status_col = CashTableFields.STATUS.value


class ManualInvestmentTransactionsRepository(CashRepository):
    """Repository for manual investment transactions."""
    table = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value
    desc_col = ManualInvestmentTransactionsTableFields.DESCRIPTION.value
    tag_col = ManualInvestmentTransactionsTableFields.TAG.value
    category_col = ManualInvestmentTransactionsTableFields.CATEGORY.value
    id_col = ManualInvestmentTransactionsTableFields.ID.value
    date_col = ManualInvestmentTransactionsTableFields.DATE.value
    provider_col = ManualInvestmentTransactionsTableFields.PROVIDER.value
    account_name_col = ManualInvestmentTransactionsTableFields.ACCOUNT_NAME.value
    account_number_col = ManualInvestmentTransactionsTableFields.ACCOUNT_NUMBER.value
    amount_col = ManualInvestmentTransactionsTableFields.AMOUNT.value
    status_col = ManualInvestmentTransactionsTableFields.STATUS.value

    def add_transaction(self, transaction: ManualInvestmentTransaction) -> bool:
        """Add a manual investment transaction (deposits are negative amounts)."""
        transaction.amount = transaction.amount * -1 if transaction.transaction_type == DEPOSIT_TYPE else transaction.amount
        return super().add_transaction(transaction)


class TransactionsRepository:
    """
    Main repository aggregating all transaction types.
    
    Provides a unified interface for accessing credit card, bank, cash,
    and manual investment transactions.
    """
    tables = [Tables.CREDIT_CARD.value, Tables.BANK.value, Tables.CASH.value]
    account_number_col = TransactionsTableFields.ACCOUNT_NUMBER.value
    type_col = TransactionsTableFields.TYPE.value
    id_col = TransactionsTableFields.ID.value
    date_col = TransactionsTableFields.DATE.value
    desc_col = TransactionsTableFields.DESCRIPTION.value
    amount_col = TransactionsTableFields.AMOUNT.value
    status_col = TransactionsTableFields.STATUS.value
    account_name_col = TransactionsTableFields.ACCOUNT_NAME.value
    provider_col = TransactionsTableFields.PROVIDER.value
    category_col = TransactionsTableFields.CATEGORY.value
    tag_col = TransactionsTableFields.TAG.value

    unique_columns = [id_col, provider_col, date_col, amount_col]

    def __init__(self, db: Session):
        """
        Initialize the transactions repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
        self.cash_repo = CashRepository(db)
        self.manual_investments_repo = ManualInvestmentTransactionsRepository(db)
        self.split_repo = SplitTransactionsRepository(db)

    def add_scraped_transactions(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Save scraped transactions to the database, avoiding duplicates.

        Parameters
        ----------
        df : pd.DataFrame
            The transaction data to save.
        table_name : str
            The target table name.
        """
        if not isinstance(df, pd.DataFrame):
            raise ValueError('df should be a pandas DataFrame object')
        if table_name not in self.tables:
            raise ValueError(f"table_name should be one of {self.tables}")

        # Get existing data to avoid duplicates
        result = self.db.execute(
            text(f'SELECT {", ".join(self.unique_columns)} FROM {table_name}')
        )
        existing_data = pd.DataFrame(result.fetchall(), columns=self.unique_columns)
        
        df = df.astype({col: str for col in self.unique_columns})
        existing_data = existing_data.astype({col: str for col in self.unique_columns})
        
        if not existing_data.empty:
            merged_df = df.merge(existing_data, on=self.unique_columns, how='left', indicator=True)
            new_rows = merged_df[merged_df['_merge'] == 'left_only'].drop(columns='_merge')
        else:
            new_rows = df

        if new_rows.empty:
            return

        # Get the engine from the session
        engine = self.db.get_bind()
        new_rows.to_sql(table_name, engine, if_exists='append', index=False)

    def add_transaction(self, transaction: CashTransaction | ManualInvestmentTransaction, service: str) -> bool:
        """Add a new transaction to the specified service table."""
        if service == Services.CASH.value:
            return self.cash_repo.add_transaction(transaction)
        elif service == Services.MANUAL_INVESTMENTS.value:
            return self.manual_investments_repo.add_transaction(transaction)
        else:
            raise ValueError(f"service must be 'cash' or 'manual_investments'. Got '{service}'")

    def get_table(
        self, 
        service: T_service | None = None, 
        query: str | None = None, 
        query_params: dict | None = None,
        include_split_parents: bool = False
    ) -> pd.DataFrame:
        """Get transactions from the specified service or all services."""
        if service is None:
            dfs = [
                self.cc_repo.get_table(query, query_params),
                self.bank_repo.get_table(query, query_params),
                self.cash_repo.get_table(query, query_params),
                self.manual_investments_repo.get_table(query, query_params)
            ]
            df = pd.concat(dfs, ignore_index=True)
        elif service in (Services.CREDIT_CARD.value, Tables.CREDIT_CARD.value):
            df = self.cc_repo.get_table(query, query_params)
        elif service in (Services.BANK.value, Tables.BANK.value):
            df = self.bank_repo.get_table(query, query_params)
        elif service in (Services.CASH.value, Tables.CASH.value):
            df = self.cash_repo.get_table(query, query_params)
        elif service in (Services.MANUAL_INVESTMENTS.value, Tables.MANUAL_INVESTMENT_TRANSACTIONS.value):
            df = self.manual_investments_repo.get_table(query, query_params)
        else:
            raise ValueError(f"Invalid service: '{service}'")

        if not include_split_parents and not df.empty and self.type_col in df.columns:
            df = df[df[self.type_col] != 'split_parent']
            
        # Add split children
        splits_df = self.split_repo.get_data()
        if not splits_df.empty:
            # Join splits with parents to get metadata
            # This is complex because parents are across multiple tables.
            # We already have the 'df' which contains (mostly) all transactions we might need.
            # But 'df' might be filtered by service or split_parents.
            # So we should probably fetch the full table for joining unless service is specified.
            
            # For each split, we need to find its parent in the appropriate table.
            children = []
            for _, split in splits_df.iterrows():
                parent_id = split[self.split_repo.transaction_id_col]
                source = split[self.split_repo.source_col]
                
                # Fetch parent to get metadata (date, desc, provider, account_name)
                try:
                    repo = self.get_repo_by_source(source)
                    parent_result = self.db.execute(
                        text(f"SELECT * FROM {repo.table} WHERE {repo.unique_id_col} = :id_val"),
                        {'id_val': parent_id}
                    ).fetchone()
                    
                    if parent_result:
                        parent_cols = repo.col_type_mapping.keys()
                        parent_dict = dict(zip(parent_cols, parent_result))
                        
                        # Create child dict
                        child = parent_dict.copy()
                        child['unique_id'] = f"split_{split[self.split_repo.id_col]}"
                        child['amount'] = split[self.split_repo.amount_col]
                        child['category'] = split[self.split_repo.category_col]
                        child['tag'] = split[self.split_repo.tag_col]
                        child['type'] = 'split_child'
                        child['source'] = source
                        children.append(child)
                except Exception:
                    continue
            
            if children:
                children_df = pd.DataFrame(children)
                # Ensure date object compatibility if needed, but dict to DF usually works
                # Filtering by service if applicable
                if service:
                    children_df = children_df[children_df['source'] == service]
                
                if not children_df.empty:
                    df = pd.concat([df, children_df], ignore_index=True)
            
        df['date'] = pd.to_datetime(df['date'])
        return df

    def split_transaction(self, unique_id: int, source: str, splits: list[dict]) -> bool:
        """
        Split a transaction into multiple parts.
        
        splits: list of {'amount': float, 'category': str, 'tag': str}
        """
        try:
            repo = self.get_repo_by_source(source)
            # 1. Mark parent
            repo.update_transaction_by_id(str(unique_id), {self.type_col: 'split_parent'})
            
            # 2. Add children
            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            for split in splits:
                self.split_repo.add_split(
                    transaction_id=unique_id,
                    source=source,
                    amount=split['amount'],
                    category=split['category'],
                    tag=split['tag']
                )
            return True
        except Exception:
            self.db.rollback()
            return False

    def revert_split(self, unique_id: int, source: str) -> bool:
        """Revert a transaction split."""
        try:
            repo = self.get_repo_by_source(source)
            # 1. Unmark parent
            repo.update_transaction_by_id(str(unique_id), {self.type_col: 'normal'})
            
            # 2. Delete children
            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            return True
        except Exception:
            self.db.rollback()
            return False

    def get_repo_by_source(self, source: str) -> ServiceRepository:
        """Get the repository instance for a specific source."""
        if source in (Services.CREDIT_CARD.value, Tables.CREDIT_CARD.value):
            return self.cc_repo
        elif source in (Services.BANK.value, Tables.BANK.value):
            return self.bank_repo
        elif source in (Services.CASH.value, Tables.CASH.value):
            return self.cash_repo
        elif source in (Services.MANUAL_INVESTMENTS.value, Tables.MANUAL_INVESTMENT_TRANSACTIONS.value):
            return self.manual_investments_repo
        else:
            raise ValueError(f"Invalid source: '{source}'")

    def bulk_update_tagging(self, transactions: list[dict], category: Optional[str], tag: Optional[str]) -> None:
        """
        Update tagging for multiple transactions.
        
        Parameters
        ----------
        transactions : list[dict]
            List of dicts with 'unique_id' and 'source'.
        category : str, optional
        tag : str, optional
        """
        for tx in transactions:
            repo = self.get_repo_by_source(tx['source'])
            # ServiceRepository update_transaction_by_id handles category/tag updates
            repo.update_transaction_by_id(str(tx['unique_id']), {
                self.category_col: category,
                self.tag_col: tag
            })

    def update_with_query(
        self, 
        query: str, 
        query_params: dict | None = None, 
        service: T_service | None = None
    ) -> int:
        """Execute an UPDATE query on the specified service(s)."""
        updated_rows = 0
        if service is None:
            updated_rows += self.cc_repo.update_with_query(query, query_params)
            updated_rows += self.bank_repo.update_with_query(query, query_params)
            updated_rows += self.cash_repo.update_with_query(query, query_params)
        elif service in (Services.CREDIT_CARD.value, Tables.CREDIT_CARD.value):
            updated_rows += self.cc_repo.update_with_query(query, query_params)
        elif service in (Services.BANK.value, Tables.BANK.value):
            updated_rows += self.bank_repo.update_with_query(query, query_params)
        elif service in (Services.CASH.value, Tables.CASH.value):
            updated_rows += self.cash_repo.update_with_query(query, query_params)
        elif service in (Services.MANUAL_INVESTMENTS.value, Tables.MANUAL_INVESTMENT_TRANSACTIONS.value):
            updated_rows += self.manual_investments_repo.update_with_query(query, query_params)
        else:
            raise ValueError(f"Invalid service: '{service}'")
        return updated_rows

    def get_latest_date_from_table(self, table_name: str) -> datetime | None:
        """Get the latest transaction date from a table."""
        result = self.db.execute(
            text(f'SELECT MAX({self.date_col}) FROM {table_name}')
        ).scalar()
        if result is not None:
            return datetime.strptime(result, '%Y-%m-%d')
        return None

    def get_all_table_names(self) -> list[str]:
        """Get all transaction table names."""
        return self.tables.copy()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for matching transactions."""
        self.cc_repo.nullify_category_and_tag(category, tag)
        self.bank_repo.nullify_category_and_tag(category, tag)
        self.cash_repo.nullify_category_and_tag(category, tag)
        self.manual_investments_repo.nullify_category_and_tag(category, tag)

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """Update category for matching transactions."""
        self.cc_repo.update_category_for_tag(old_category, new_category, tag)
        self.bank_repo.update_category_for_tag(old_category, new_category, tag)
        self.cash_repo.update_category_for_tag(old_category, new_category, tag)
        self.manual_investments_repo.update_category_for_tag(old_category, new_category, tag)

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for all transactions with the category."""
        self.cc_repo.nullify_category(category)
        self.bank_repo.nullify_category(category)
        self.cash_repo.nullify_category(category)
        self.manual_investments_repo.nullify_category(category)

    def get_transaction_by_id(self, transaction_id: int) -> pd.Series:
        """Get a transaction by its ID."""
        df = self.get_table()
        transaction = df[df[self.id_col] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found.")
        elif len(transaction) > 1:
            raise ValueError(f"Multiple transactions found with ID {transaction_id}.")
        return transaction.iloc[0]
