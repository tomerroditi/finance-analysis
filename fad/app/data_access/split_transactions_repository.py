from typing import Literal

import pandas as pd
from sqlalchemy import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import Tables, SplitTransactionsTableFields


class SplitTransactionsRepository:
    table = Tables.SPLIT_TRANSACTIONS.value
    id_col = SplitTransactionsTableFields.ID.value
    transaction_id_col = SplitTransactionsTableFields.TRANSACTION_ID.value
    service_col = SplitTransactionsTableFields.SERVICE.value
    amount_col = SplitTransactionsTableFields.AMOUNT.value
    category_col = SplitTransactionsTableFields.CATEGORY.value
    tag_col = SplitTransactionsTableFields.TAG.value

    def __init__(self, conn: SQLConnection):
        """
        Initializes the SplitTransactionsRepository with a database connection.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.conn = conn
        self.assure_table_exists()

    def get_data(self, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """
        Get all splits for a specific service.
        """
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table} WHERE service = :service"
            params = {"service": service}
            result = s.execute(text(query), params)
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df
        
    def get_splits_for_transaction(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """
        Get all splits for a specific transaction.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing all splits for the transaction.
        """
        with self.conn.session as s:
            query = f"""
                SELECT * FROM {self.table}
                WHERE {self.transaction_id_col} = :transaction_id_val
                AND {self.service_col} = :service_val
            """
            params = {
                'transaction_id_val': transaction_id,
                'service_val': service
            }
            result = s.execute(text(query), params)
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def add_split(self, transaction_id: int, service: Literal['credit_card', 'bank'], amount: float, category: str, tag: str) -> int:
        """
        Add a new split for a transaction.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.
        amount : float
            The amount of the split.
        category : str
            The category of the split.
        tag : str
            The tag of the split.

        Returns
        -------
        int
            The ID of the newly created split.
        """
        with self.conn.session as s:
            query = f"""
                INSERT INTO {self.table} (
                    {self.transaction_id_col}, {self.service_col}, {self.amount_col}, {self.category_col}, {self.tag_col}
                ) VALUES (
                    :transaction_id_val, :service_val, :amount_val, :category_val, :tag_val
                )
                RETURNING {self.id_col}
            """
            params = {
                'transaction_id_val': transaction_id,
                'service_val': service,
                'amount_val': amount,
                'category_val': category,
                'tag_val': tag
            }
            result = s.execute(text(query), params)
            split_id = result.fetchone()[0]
            s.commit()
            return split_id

    def update_split(self, split_id: int, amount: float, category: str, tag: str) -> None:
        """
        Update an existing split.

        Parameters
        ----------
        split_id : int
            The ID of the split to update.
        amount : float
            The new amount of the split.
        category : str
            The new category of the split.
        tag : str
            The new tag of the split.

        Returns
        -------
        None
        """
        with self.conn.session as s:
            query = f"""
                UPDATE {self.table}
                SET {self.amount_col} = :amount_val, {self.category_col} = :category_val, {self.tag_col} = :tag_val
                WHERE {self.id_col} = :split_id_val
            """
            params = {
                'amount_val': amount,
                'category_val': category,
                'tag_val': tag,
                'split_id_val': split_id
            }
            s.execute(text(query), params)
            s.commit()

    def delete_split(self, split_id: int) -> None:
        """
        Delete a split.

        Parameters
        ----------
        split_id : int
            The ID of the split to delete.

        Returns
        -------
        None
        """
        with self.conn.session as s:
            query = f"""
                DELETE FROM {self.table}
                WHERE {self.id_col} = :split_id_val
            """
            params = {
                'split_id_val': split_id
            }
            s.execute(text(query), params)
            s.commit()

    def delete_all_splits_for_transaction(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> None:
        """
        Delete all splits for a specific transaction.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        with self.conn.session as s:
            query = f"""
                DELETE FROM {self.table}
                WHERE {self.transaction_id_col} = :transaction_id_val
                AND {self.service_col} = :service_val
            """
            params = {
                'transaction_id_val': transaction_id,
                'service_val': service
            }
            s.execute(text(query), params)
            s.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """
        Set category and tag to NULL for all splits with the specified category and tag (optionally filtered by service).
        """
        with self.conn.session as s:
            query = f"""
                UPDATE {self.table}
                SET {self.category_col} = NULL, {self.tag_col} = NULL
                WHERE {self.category_col} = :category_val AND {self.tag_col} = :tag_val
            """
            params = {'category_val': category, 'tag_val': tag}
            s.execute(text(query), params)
            s.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """
        Update the category to new_category for all splits with the specified old_category and tag.
        """
        with self.conn.session as s:
            query = f"""
                UPDATE {self.table}
                SET {self.category_col} = :new_category
                WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
            """
            params = {'new_category': new_category, 'old_category': old_category, 'tag': tag}
            s.execute(text(query), params)
            s.commit()

    def assure_table_exists(self):
        """
        Ensure that the split transactions table exists in the database.
        If it doesn't exist, create it.

        Returns
        -------
        None
        """
        with self.conn.session as s:
            s.execute(
                text(f'CREATE TABLE IF NOT EXISTS {self.table} ('
                     f'{self.id_col} INTEGER PRIMARY KEY, '
                     f'{self.transaction_id_col} INTEGER, '
                     f'{self.service_col} TEXT, '
                     f'{self.amount_col} REAL, '
                     f'{self.category_col} TEXT, '
                     f'{self.tag_col} TEXT'
                     f');'
                )
            )
            s.commit()