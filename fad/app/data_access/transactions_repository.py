from datetime import datetime
from typing import Literal

import pandas as pd
from sqlalchemy import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import Tables, CreditCardTableFields, BankTableFields, TransactionsTableFields


class TransactionsRepository:
    """
    Repository for basic CRUD operations on transactions data.
    Contains only data access logic, no business logic.
    """
    tables = [Tables.CREDIT_CARD.value, Tables.BANK.value]
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

    def get_table(self, service: Literal['credit_card', 'bank'] | None = None) -> pd.DataFrame:
        """
        Get the transactions table for the specified service.

        Parameters
        ----------
        service : Literal['credit_card', 'bank'] | None
            The service of the transactions, should be one of 'credit_card' or 'bank'. if not specified, returns all
            transactions

        Returns
        -------
        pd.DataFrame
            The transactions table as a DataFrame.
        """
        if service is None:
            return pd.concat([self.cc_repo.get_table(), self.bank_repo.get_table()], ignore_index=True)
        elif service == 'credit_card':
            return self.cc_repo.get_table()
        elif service == 'bank':
            return self.bank_repo.get_table()
        else:
            raise ValueError(f"service must be either 'credit_card' or 'bank'. Got '{service}'")

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

    def get_data_by_description(self, description: str, service: Literal['credit_card', 'bank'], account_number: str = None) -> pd.DataFrame:
        """
        Get transactions data by description for the specified service.

        Parameters
        ----------
        description : str
            The description to filter transactions by.
        service : str
            The service of the transactions, should be one of 'credit_card' or 'bank'.
        account_number : str, optional
            The account number to filter transactions by (only applicable for bank transactions).

        Returns
        -------
        pd.DataFrame
            The filtered transactions data as a DataFrame.
        """
        if service == 'credit_card':
            return self.cc_repo.get_data_by_description(description)
        elif service == 'bank':
            return self.bank_repo.get_data_by_description(description, account_number)
        else:
            raise ValueError(f"service must be either 'credit_card' or 'bank'. Got '{service}'")

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
    desc_col: str
    tag_col: str
    category_col: str
    name_col: str
    id_col: str
    date_col: str
    provider_col: str
    account_name_col: str
    account_number_col: str
    amount_col: str

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
                    {self.id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                    {self.date_col} DATE,
                    {self.provider_col} TEXT,
                    {self.account_name_col} TEXT,
                    {self.account_number_col} TEXT,
                    {self.desc_col} TEXT,
                    {self.amount_col} REAL,
                    {self.category_col} TEXT,
                    {self.tag_col} TEXT
                )
            """
            s.execute(text(my_query))
            s.commit()

    def get_table(self) -> pd.DataFrame:
        """
        Get the transactions table as a DataFrame.
        """
        table = self.conn.query(f'SELECT * FROM {self.table};', ttl=0)
        return table

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
                params = {'id_val': transaction_id}

                for field, value in updates.items():
                    if value is not None:  # Only update non-None values
                        param_name = f"{field}_val"
                        set_clauses.append(f"{field} = :{param_name}")
                        params[param_name] = value

                if not set_clauses:
                    return False

                my_query = f"""
                    UPDATE {self.table}
                    SET {', '.join(set_clauses)}
                    WHERE {self.id_col} = :id_val
                """

                result = s.execute(text(my_query), params)
                s.commit()
                return result.rowcount > 0
        except Exception:
            return False


class CreditCardRepository(ServiceRepository):
    table = Tables.CREDIT_CARD.value
    desc_col = CreditCardTableFields.DESCRIPTION.value
    tag_col = CreditCardTableFields.TAG.value
    category_col = CreditCardTableFields.CATEGORY.value
    name_col = CreditCardTableFields.DESCRIPTION.value
    id_col = CreditCardTableFields.ID.value
    date_col = CreditCardTableFields.DATE.value
    provider_col = CreditCardTableFields.PROVIDER.value
    account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
    account_number_col = CreditCardTableFields.ACCOUNT_NUMBER.value
    amount_col = CreditCardTableFields.AMOUNT.value
    type_col = CreditCardTableFields.TYPE.value
    status_col = CreditCardTableFields.STATUS.value

    def update_tagging_by_name(self, name: str, category: str, tag: str) -> None:
        """
        Update the tags of credit card transactions in the database.

        Parameters
        ----------
        name : str
            The name of the transaction.
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
                WHERE {self.desc_col} = :name_val
            """
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name
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

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """
        Update the category to new_category for all credit card transactions with the specified old_category and tag.
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

    def assure_table_exists(self):
        with self.conn.session as s:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {self.table} ('
                     f'{self.id_col} INTEGER PRIMARY KEY, '
                     f'{self.date_col} TEXT, '
                     f'{self.amount_col} REAL, '
                     f'{self.desc_col} TEXT, '
                     f'{self.tag_col} TEXT, '
                     f'{self.category_col} TEXT, '
                     f'{self.provider_col} TEXT, '
                     f'{self.account_name_col} TEXT, '
                     f'{self.account_number_col} TEXT, '
                     f'{self.status_col} TEXT, '
                     f'{self.type_col} TEXT'
                     f');'
                )
            )
            s.commit()

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

    def get_data_by_description(self, description: str) -> pd.DataFrame:
        """
        Get credit card transactions data by description.

        Parameters
        ----------
        description : str
            The description to filter transactions by.

        Returns
        -------
        pd.DataFrame
            The filtered credit card transactions data as a DataFrame.
        """
        with self.conn.session as s:
            query = f'SELECT * FROM {self.table} WHERE {self.desc_col} = :description'
            params = {'description': description}
            result = s.execute(text(query), params).fetchall()
            return pd.DataFrame(result)


class BankRepository(ServiceRepository):
    table = Tables.BANK.value
    desc_col = BankTableFields.DESCRIPTION.value
    tag_col = BankTableFields.TAG.value
    category_col = BankTableFields.CATEGORY.value
    name_col = BankTableFields.DESCRIPTION.value
    id_col = BankTableFields.ID.value
    account_number_col = BankTableFields.ACCOUNT_NUMBER.value
    date_col = BankTableFields.DATE.value
    provider_col = BankTableFields.PROVIDER.value
    account_name_col = BankTableFields.ACCOUNT_NAME.value
    amount_col = BankTableFields.AMOUNT.value
    type_col = BankTableFields.TYPE.value
    status_col = BankTableFields.STATUS.value

    def update_tagging_by_name_and_account_number(self, name: str, account_number: str, category: str, tag: str) -> None:
        """
        Update the tags of bank transactions in the database.

        Parameters
        ----------
        name : str
            The name of the transaction.
        account_number : str
            The account number of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = :category_val, {self.tag_col} = :tag_val
                WHERE {self.desc_col} = :name_val AND {self.account_number_col} = :account_number_val
            """
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name,
                'account_number_val': account_number
            }
            s.execute(text(my_query), params)
            s.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """
        Set category and tag to NULL for all bank transactions with the specified category and tag (optionally filtered by account_number).
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

    def assure_table_exists(self):
        with self.conn.session as s:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {self.table} ('
                     f'{self.id_col} INTEGER PRIMARY KEY, '
                     f'{self.date_col} TEXT, '
                     f'{self.amount_col} REAL, '
                     f'{self.desc_col} TEXT, '
                     f'{self.tag_col} TEXT, '
                     f'{self.category_col} TEXT, '
                     f'{self.provider_col} TEXT, '
                     f'{self.account_name_col} TEXT, '
                     f'{self.account_number_col} TEXT, '
                     f'{self.status_col} TEXT, '
                     f'{self.type_col} TEXT'
                     f');'
                )
            )
            s.commit()

    def nullify_category(self, category: str) -> None:
        """
        Set category and tag to NULL for all bank transactions with the specified category.
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

    def get_data_by_description(self, description: str, account_number: str = None) -> pd.DataFrame:
        """
        Get bank transactions data by description.

        Parameters
        ----------
        description : str
            The description to filter transactions by.
        account_number : str, optional
            The account number to filter transactions by (if provided, filters by account number as well).

        Returns
        -------
        pd.DataFrame
            The filtered bank transactions data as a DataFrame.
        """
        with self.conn.session as s:
            if account_number:
                query = f'SELECT * FROM {self.table} WHERE {self.desc_col} = :description AND {self.account_number_col} = :account_number'
                params = {'description': description, 'account_number': account_number}
            else:
                query = f'SELECT * FROM {self.table} WHERE {self.desc_col} = :description'
                params = {'description': description}
            result = s.execute(text(query), params).fetchall()
            return pd.DataFrame(result)