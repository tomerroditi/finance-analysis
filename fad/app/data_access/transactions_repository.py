from datetime import datetime
from typing import Literal

import pandas as pd
from sqlalchemy import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import Tables, CreditCardTableFields, BankTableFields, TransactionsTableFields, SplitTransactionsTableFields
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository


class TransactionsRepository:
    tables = [Tables.CREDIT_CARD.value, Tables.BANK.value]
    split_table = Tables.SPLIT_TRANSACTIONS.value
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

    analysis_cols = [
        TransactionsTableFields.DATE.value,
        TransactionsTableFields.PROVIDER.value,
        TransactionsTableFields.ACCOUNT_NAME.value,
        TransactionsTableFields.ACCOUNT_NUMBER.value,
        TransactionsTableFields.DESCRIPTION.value,
        TransactionsTableFields.AMOUNT.value,
        TransactionsTableFields.CATEGORY.value,
        TransactionsTableFields.TAG.value,
    ]

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
        self.split_repo = SplitTransactionsRepository(conn)

    def get_table(self, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """
        Get the transactions table for the specified service.

        Parameters
        ----------
        service : str
            The service of the transactions, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        pd.DataFrame
            The transactions table as a DataFrame.
        """
        if service == 'credit_card':
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

    def get_table_for_analysis(self, service: Literal['credit_card', 'bank'] = 'credit_card') -> pd.DataFrame:
        """
        Returns the transactions table for the specified service (credit card or bank), replacing rows with split transactions by their splits.
        The returned DataFrame has the same columns as the original, with split rows replacing the originals, and all other rows unchanged.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            The service for which to return the table ('credit_card' or 'bank').
        """
        if service == 'credit_card':
            df = self.cc_repo.get_table().copy()
        elif service == 'bank':
            df = self.bank_repo.get_table().copy()
        else:
            raise ValueError("service must be either 'credit_card' or 'bank'")

        # Get all splits for this service
        split_df = self.split_repo.get_data(service)
        if split_df.empty:
            return df[self.analysis_cols]

        # Prepare for merging: drop original transactions that have splits, and add split rows
        split_ids = set(split_df['transaction_id'])
        mask = df[self.id_col].isin(split_ids)
        base_df = df[~mask].copy()

        # For each split, get the original transaction row, update amount/category/tag, and append
        split_rows = []
        for id_, split_group in split_df.groupby(self.split_repo.id_col):
            orig_row = df[df[self.id_col] == id_]
            if orig_row.empty:
                continue
            for _, split in split_group.iterrows():
                split_row = orig_row.copy()
                split_row[self.amount_col] = split[self.split_repo.amount_col]
                split_row[self.category_col] = split[self.split_repo.category_col]
                split_row[self.tag_col] = split[self.split_repo.tag_col]
                split_rows.append(split_row)

        if split_rows:
            split_rows_df = pd.DataFrame(split_rows)
            result_df = pd.concat([base_df, split_rows_df], ignore_index=True)
        else:
            result_df = base_df

        return result_df[self.analysis_cols].reset_index(drop=True)


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

    def update_tagging_by_id(self, id_: int, category: str, tag: str) -> None:
        """
        Update the tags of bank transactions in the database by transaction ID.

        Parameters
        ----------
        id_ : int
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
