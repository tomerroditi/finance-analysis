from datetime import datetime
from typing import Literal, Optional
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import (
    Tables, CreditCardTableFields, BankTableFields, CashTableFields, TransactionsTableFields, Services,
    ManualInvestmentTransactionsTableFields
)

DEPOSIT_TYPE = 'deposit'
WITHDRAWAL_TYPE = 'withdrawal'


@dataclass
class CashTransaction:
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
    date: datetime
    account_name: str
    desc: str
    amount: float
    transaction_type: Literal[DEPOSIT_TYPE, WITHDRAWAL_TYPE]
    provider: str
    account_number: str
    category: str
    tag: str


T_service = Literal[
    Services.CREDIT_CARD, Services.BANK, Services.CASH, Services.MANUAL_INVESTMENTS,
    Tables.CREDIT_CARD, Tables.BANK, Tables.CASH, Tables.MANUAL_INVESTMENT_TRANSACTIONS
]


class TransactionsRepository:
    """
    Repository for basic CRUD operations on transactions data.
    Contains only data access logic, no business logic.
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

    def __init__(self, conn: SQLConnection):
        """
        Initializes the TransactionsRepository with a database connection.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.conn = conn
        self.cc_repo = CreditCardRepository(conn)
        self.bank_repo = BankRepository(conn)
        self.cash_repo = CashRepository(conn)
        self.manual_investments_repo = ManualInvestmentTransactionsRepository(conn)

    def add_scraped_transactions(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Save the data to the database

        Parameters
        ----------
        df: pd.DataFrame
            the data to save to the database
        table_name: str
            the name of the table to save the data to
        """
        if not isinstance(df, pd.DataFrame):
            raise ValueError('df should be a pandas DataFrame object')
        if table_name not in self.tables:
            raise ValueError(f"table_name should be one of {self.tables}")

        # remove rows that are in the database already by full comparison (id is not guaranteed to be unique since we scrape from multiple sources)
        existing_data = self.conn.query(f'SELECT {", ".join(self.unique_columns)} FROM {table_name}')
        df = df.astype({col: str for col in self.unique_columns})
        existing_data = existing_data.astype({col: str for col in self.unique_columns})
        if not existing_data.empty:
            merged_df = df.merge(existing_data, on=self.unique_columns, how='left', indicator=True)
            new_rows = merged_df[merged_df['_merge'] == 'left_only'].drop(columns='_merge')
        else:
            new_rows = df

        if new_rows.empty:
            return

        new_rows.to_sql(table_name, self.conn.session.bind, if_exists='append', index=False)

    def add_transaction(self, transaction: CashTransaction | ManualInvestmentTransaction, service: str) -> bool:
        """
        Add a new transaction to the database.

        Parameters
        ----------
        transaction : CashTransaction | ManualInvestmentTransaction
            The transaction to add.
        service : str
            The service of the transaction, should be "cash" or "manual_investments".

        Returns
        -------
        bool
            True if the transaction was added successfully, False otherwise.
        """
        if service == Services.CASH.value:
            repo = self.cash_repo
        elif service == Services.MANUAL_INVESTMENTS.value:
            repo = self.manual_investments_repo
        else:
            raise ValueError(f"service must be 'cash'. Got '{service}'")

        return repo.add_transaction(transaction)

    def get_table(self, service: T_service | None = None, query: str | None = None, query_params: dict | None = None) -> pd.DataFrame:
        """
        Get the transactions table for the specified service.

        Parameters
        ----------
        service : Literal['credit_card', 'bank', 'cash'] | None
            The service of the transactions, should be one of 'credit_card', 'bank' or 'cash'. if not specified, returns
            all transactions
        query : str, optional
            An optional SQL query to filter the transactions. must comply with SQLAlchemy text() requirements.
        query_params : dict, optional
            parameters for the SQL query. must comply with the query parameters.

        Returns
        -------
        pd.DataFrame
            The transactions table as a DataFrame.
        """
        if service is None:
            return pd.concat(
                [
                    self.cc_repo.get_table(query, query_params),
                    self.bank_repo.get_table(query, query_params),
                    self.cash_repo.get_table(query, query_params),
                    self.manual_investments_repo.get_table(query, query_params)
                ],
                ignore_index=True
            )
        elif service == Services.CREDIT_CARD.value or service == Tables.CREDIT_CARD.value:
            return self.cc_repo.get_table(query, query_params)
        elif service == Services.BANK.value or service == Tables.BANK.value:
            return self.bank_repo.get_table(query, query_params)
        elif service == Services.CASH.value or service == Tables.CASH.value:
            return self.cash_repo.get_table(query, query_params)
        elif service == Services.MANUAL_INVESTMENTS.value or service == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value:
            return self.manual_investments_repo.get_table(query, query_params)
        else:
            raise ValueError(f"service must be either 'credit_card', 'bank' or 'cash'. Got '{service}'")

    def update_with_query(self, query: str, query_params: dict | None = None, service: T_service | None = None) -> int:
        """
        Update the tags of transactions in the database based on a custom SQL query.

        Parameters
        ----------
        query : str
            The SQL query to filter the transactions to update. must comply with SQLAlchemy text() requirements.
        query_params : dict, optional
            parameters for the SQL query. must comply with the query parameters.
        service : Literal['credit_card', 'bank'] | None
            The service of the transactions, should be one of 'credit_card', 'bank' or 'cash'. if not specified, updates all transactions

        Returns
        -------
        int
            The number of rows updated.
        """
        updated_rows = 0
        if service is None:
            updated_rows += self.cc_repo.update_with_query(query, query_params)
            updated_rows += self.bank_repo.update_with_query(query, query_params)
            updated_rows += self.cash_repo.update_with_query(query, query_params)
        elif service == Services.CREDIT_CARD.value or service == Tables.CREDIT_CARD.value:
            updated_rows += self.cc_repo.update_with_query(query, query_params)
        elif service == Services.BANK.value or service == Tables.BANK.value:
            updated_rows += self.bank_repo.update_with_query(query, query_params)
        elif service == Services.CASH.value or service == Tables.CASH.value:
            updated_rows += self.cash_repo.update_with_query(query, query_params)
        elif service == Services.MANUAL_INVESTMENTS.value or service == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value:
            updated_rows += self.manual_investments_repo.update_with_query(query, query_params)
        else:
            raise ValueError(f"service must be either 'credit_card', 'bank' or 'cash'. Got '{service}'")

        return updated_rows

    def get_latest_date_from_table(self, table_name: str) -> datetime | None:
        """
        Get the latest date from a specific table.

        Parameters
        ----------
        table_name : str
            The name of the table to query.

        Returns
        -------
        datetime | None
            The latest date from the table, or None if no data exists.
        """
        query = f'SELECT MAX({self.date_col}) FROM {table_name}'
        result = self.conn.query(query, ttl=0).iloc[0, 0]
        if result is not None:
            return datetime.strptime(result, '%Y-%m-%d')
        return None

    def get_all_table_names(self) -> list[str]:
        """
        Get all transaction table names.

        Returns
        -------
        list[str]
            List of all transaction table names.
        """
        return self.tables.copy()
    
    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """
        Set category and tag to NULL for all transactions with the specified category and tag.

        Parameters
        ----------
        category : str
            The category to nullify.
        tag : str
            The tag to nullify.
        """
        self.cc_repo.nullify_category_and_tag(category, tag)
        self.bank_repo.nullify_category_and_tag(category, tag)

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """
        Update the category to new_category for all transactions with the specified old_category and tag.
        """
        self.cc_repo.update_category_for_tag(old_category, new_category, tag)
        self.bank_repo.update_category_for_tag(old_category, new_category, tag)

    def nullify_category(self, category: str) -> None:
        """
        Set category and tag to NULL for all transactions with the specified category.
        """
        self.cc_repo.nullify_category(category)
        self.bank_repo.nullify_category(category)

    def get_transaction_by_id(self, transaction_id: int) -> pd.Series:
        """
        Get a transaction by its ID.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.

        Returns
        -------
        pd.Series
            The transaction data.
        """
        df = self.get_table()
        transaction = df[df[self.id_col] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found in transactions.")
        elif len(transaction) > 1:
            raise ValueError(f"Multiple transactions found with ID {transaction_id}.")
        return transaction.iloc[0]


class ServiceRepository:
    """
    Abstract base class for repositories that handle transactions data.
    This class defines the common interface for repositories that manage transactions data.
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

    unique_columns = [id_col, provider_col, date_col, amount_col]

    col_type_mapping = {
        unique_id_col: "INTEGER PRIMARY KEY AUTOINCREMENT",
        id_col: "TEXT",
        date_col: "TEXT",
        provider_col: "TEXT",
        account_name_col: "TEXT",
        account_number_col: "TEXT",
        desc_col: "TEXT",
        amount_col: "REAL",
        category_col: "TEXT DEFAULT NULL",
        tag_col: "TEXT DEFAULT NULL",
        type_col: "TEXT DEFAULT 'normal'",
        status_col: "TEXT DEFAULT 'completed'"
    }

    def __init__(self, conn: SQLConnection):
        """
        Initializes the repository with a database connection.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.conn = conn
        self.assure_table_exists()

    def assure_table_exists(self) -> None:
        """
        Ensure that the transactions table exists in the database.
        If it does not exist, create it with the necessary columns.
        """
        with self.conn.session as s:
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
                    {self.type_col} {self.col_type_mapping[self.type_col]},
                    {self.status_col} {self.col_type_mapping[self.status_col]},
                    UNIQUE ({', '.join(self.unique_columns)})
                )
            """
            s.execute(text(my_query))
            s.commit()

    def get_table(self, query: str | None = None, params: dict | None = None) -> pd.DataFrame:
        """
        Get the transactions table as a DataFrame.

        Parameters
        ----------
        query : str, optional
            An optional SQL query to filter the transactions. must comply with SQLAlchemy text() requirements.
        params : dict, optional
            parameters for the SQL query. must comply with the query parameters.

        Returns
        -------
        pd.DataFrame
            The transactions table as a DataFrame.
        """
        if query:
            result = self.conn.session.execute(text(query), params)
            table = pd.DataFrame(result.fetchall())
        else:
            table = self.conn.query(f'SELECT * FROM {self.table};', ttl=0)
        return table

    def update_with_query(self, query: str, query_params: dict | None = None) -> int:
        """
        Update the tags of transactions in the database based on a custom SQL query.

        Parameters
        ----------
        query : str
            The SQL query to filter the transactions to update. must comply with SQLAlchemy text() requirements.
        query_params : dict, optional
            parameters for the SQL query. must comply with the query parameters.

        Returns
        -------
        int
            The number of rows updated.
        """
        if not query.strip().lower().startswith('update'):
            raise ValueError("The query must be an UPDATE statement.")

        with self.conn.session as s:
            result = s.execute(text(query), query_params)
            s.commit()
            return result.rowcount

    def get_table_columns(self) -> list[str]:
        """
        Get the columns of the transactions table.

        Returns
        -------
        list[str]
            A list of column names in the transactions table.
        """
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
        """
        Update the tags of bank transactions in the database by transaction ID.

        Parameters
        ----------
        id_ : str
            The ID of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.

        Returns
        -------
        None
        """
        with self.conn.session as s:
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
            s.execute(text(my_query), params)
            s.commit()

    def update_transaction_by_id(self, transaction_id: str, updates: dict) -> bool:
        """
        Update a transaction by ID with the given field updates.

        Parameters
        ----------
        transaction_id : str
            The ID of the transaction to update.
        updates : dict
            Dictionary of field names and their new values.

        Returns
        -------
        bool
            True if the update was successful, False otherwise.
        """
        if not updates:
            return False

        try:
            with self.conn.session as s:
                # Build the SET clause dynamically
                set_clauses = []
                params = {'id_val': int(transaction_id)}  # Ensure transaction_id is an integer (and not int64 or str)

                for field, value in updates.items():
                    param_name = f"{field}_val"
                    set_clauses.append(f"{field} = :{param_name}")
                    params[param_name] = value

                if not set_clauses:
                    return False

                my_query = f"""
                    UPDATE {self.table}
                    SET {', '.join(set_clauses)}
                    WHERE {self.unique_id_col} = :id_val
                """

                result = s.execute(text(my_query), params)
                s.commit()
                return result.rowcount > 0
        except Exception:
            return False

    def nullify_category(self, category: str) -> None:
        """
        Set category and tag to NULL for all credit card transactions with the specified category.
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = NULL, {self.tag_col} = NULL
                WHERE {self.category_col} = :category_val
            """
            params = {'category_val': category}
            s.execute(text(my_query), params)
            s.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """
        Update the category to new_category for all bank transactions with the specified old_category and tag.
        """
        with self.conn.session as s:
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
            s.execute(text(my_query), params)
            s.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """
        Set category and tag to NULL for all credit card transactions with the specified category and tag.
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = NULL, {self.tag_col} = NULL
                WHERE {self.category_col} = :category_val AND {self.tag_col} = :tag_val
            """
            params = {
                'category_val': category,
                'tag_val': tag
            }
            s.execute(text(my_query), params)
            s.commit()

    def add_transaction(self, transaction: CashTransaction | ManualInvestmentTransaction) -> bool:
        """
        Add a new cash transaction to the database.

        Parameters
        ----------
        transaction : CashTransaction | ManualInvestmentTransaction
            The cash transaction to add.

        Returns
        -------
        bool
            True if the transaction was added successfully, False otherwise.
        """
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
            with self.conn.session as s:
                max_id = s.execute(
                    text(f'SELECT MAX({self.id_col}) FROM {self.table}')
                ).scalar()
                params['id_val'] = (int(max_id) + 1) if max_id is not None else 1
                s.execute(text(my_query), params)
                s.commit()
                return True
        except Exception:
            return False


class CreditCardRepository(ServiceRepository):
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

    def delete_transaction_by_id(self, transaction_id: str) -> bool:
        """
        Delete a cash transaction by its ID.

        Parameters
        ----------
        transaction_id : str
            The ID of the transaction to delete.

        Returns
        -------
        bool
            True if the transaction was deleted successfully, False otherwise.
        """
        my_query = f"""
            DELETE FROM {self.table}
            WHERE {self.unique_id_col} = :id_val
        """
        params = {'id_val': int(transaction_id)}  # Ensure transaction_id is an integer (and not int64 or str)
        try:
            with self.conn.session as s:
                result = s.execute(text(my_query), params)
                s.commit()
                return result.rowcount > 0
        except Exception:
            return False


class ManualInvestmentTransactionsRepository(CashRepository):
    """
    Repository for managing manual investment transaction records.

    Handles CRUD operations for manual transactions that cannot be scraped,
    such as old transactions or transactions from unsupported sources.
    """
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
        """
        Add a new cash transaction to the database.

        Parameters
        ----------
        transaction : ManualInvestmentTransaction
            The cash transaction to add.

        Returns
        -------
        bool
            True if the transaction was added successfully, False otherwise.
        """
        transaction.amount = transaction.amount * -1 if transaction.transaction_type == DEPOSIT_TYPE else transaction.amount
        return super().add_transaction(transaction)