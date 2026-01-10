"""
Split transactions repository with pure SQLAlchemy (no Streamlit dependencies).

This module provides data access for split transaction operations.
"""
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.naming_conventions import Tables, SplitTransactionsTableFields


class SplitTransactionsRepository:
    """
    Repository for managing split transaction records.
    
    Handles transactions that have been divided into multiple category/tag parts.
    """
    table = Tables.SPLIT_TRANSACTIONS.value
    id_col = SplitTransactionsTableFields.ID.value
    transaction_id_col = SplitTransactionsTableFields.TRANSACTION_ID.value
    source_col = "source"  # Not in enum yet, adding manually or I could update the enum
    amount_col = SplitTransactionsTableFields.AMOUNT.value
    category_col = SplitTransactionsTableFields.CATEGORY.value
    tag_col = SplitTransactionsTableFields.TAG.value

    def __init__(self, db: Session):
        """
        Initialize the split transactions repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._assure_table_exists()

    def _assure_table_exists(self) -> None:
        """Create the split transactions table if it doesn't exist."""
        self.db.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    {self.id_col} INTEGER PRIMARY KEY,
                    {self.transaction_id_col} INTEGER,
                    {self.source_col} TEXT,
                    {self.amount_col} REAL,
                    {self.category_col} TEXT,
                    {self.tag_col} TEXT
                )
            """)
        )
        self.db.commit()

    def get_data(self) -> pd.DataFrame:
        """Get all split transactions."""
        result = self.db.execute(text(f"SELECT * FROM {self.table}"))
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def get_splits_for_transaction(self, transaction_id: int, source: str) -> pd.DataFrame:
        """Get all splits for a specific transaction."""
        result = self.db.execute(
            text(f"""
                SELECT * FROM {self.table}
                WHERE {self.transaction_id_col} = :transaction_id_val
                AND {self.source_col} = :source_val
            """),
            {'transaction_id_val': transaction_id, 'source_val': source}
        )
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def add_split(self, transaction_id: int, source: str, amount: float, category: str, tag: str) -> int:
        """
        Add a new split for a transaction.

        Returns
        -------
        int
            The ID of the newly created split.
        """
        result = self.db.execute(
            text(f"""
                INSERT INTO {self.table} (
                    {self.transaction_id_col}, {self.source_col}, {self.amount_col}, {self.category_col}, {self.tag_col}
                ) VALUES (
                    :transaction_id_val, :source_val, :amount_val, :category_val, :tag_val
                )
            """),
            {
                'transaction_id_val': transaction_id,
                'source_val': source,
                'amount_val': amount,
                'category_val': category,
                'tag_val': tag
            }
        )
        self.db.commit()
        return result.lastrowid

    def update_split(self, split_id: int, amount: float, category: str, tag: str) -> None:
        """Update an existing split."""
        self.db.execute(
            text(f"""
                UPDATE {self.table}
                SET {self.amount_col} = :amount_val, 
                    {self.category_col} = :category_val, 
                    {self.tag_col} = :tag_val
                WHERE {self.id_col} = :split_id_val
            """),
            {
                'amount_val': amount,
                'category_val': category,
                'tag_val': tag,
                'split_id_val': split_id
            }
        )
        self.db.commit()

    def delete_split(self, split_id: int) -> None:
        """Delete a split by ID."""
        self.db.execute(
            text(f"DELETE FROM {self.table} WHERE {self.id_col} = :split_id_val"),
            {'split_id_val': split_id}
        )
        self.db.commit()

    def delete_all_splits_for_transaction(self, transaction_id: int, source: str) -> None:
        """Delete all splits for a specific transaction."""
        self.db.execute(
            text(f"""
                DELETE FROM {self.table} 
                WHERE {self.transaction_id_col} = :transaction_id_val
                AND {self.source_col} = :source_val
            """),
            {'transaction_id_val': transaction_id, 'source_val': source}
        )
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for matching splits."""
        self.db.execute(
            text(f"""
                UPDATE {self.table}
                SET {self.category_col} = NULL, {self.tag_col} = NULL
                WHERE {self.category_col} = :category_val AND {self.tag_col} = :tag_val
            """),
            {'category_val': category, 'tag_val': tag}
        )
        self.db.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """Update category for splits with specified old_category and tag."""
        self.db.execute(
            text(f"""
                UPDATE {self.table}
                SET {self.category_col} = :new_category
                WHERE {self.category_col} = :old_category AND {self.tag_col} = :tag
            """),
            {'new_category': new_category, 'old_category': old_category, 'tag': tag}
        )
        self.db.commit()

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for splits with specified category."""
        self.db.execute(
            text(f"""
                UPDATE {self.table}
                SET {self.category_col} = NULL, {self.tag_col} = NULL
                WHERE {self.category_col} = :category_val
            """),
            {'category_val': category}
        )
        self.db.commit()
