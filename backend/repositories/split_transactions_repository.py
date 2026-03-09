"""
Split transactions repository with SQLAlchemy ORM.
"""

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.models.transaction import SplitTransaction


class SplitTransactionsRepository:
    """
    Repository for managing split transaction records using ORM.
    """

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def _assure_table_exists(self) -> None:
        pass

    def get_data(self) -> pd.DataFrame:
        """Get all split transactions.

        Returns
        -------
        pd.DataFrame
            All split transaction rows with columns id, transaction_id, source,
            amount, category, tag.
        """
        stmt = select(SplitTransaction)
        return pd.read_sql(stmt, self.db.bind)

    def get_splits_for_transaction(
        self, transaction_id: int, source: str
    ) -> pd.DataFrame:
        """Get all splits for a specific transaction.

        Parameters
        ----------
        transaction_id : int
            Unique ID of the parent transaction.
        source : str
            Table name of the parent transaction's source (e.g. 'bank_transactions').

        Returns
        -------
        pd.DataFrame
            Split rows belonging to the specified parent transaction.
        """
        stmt = select(SplitTransaction).where(
            SplitTransaction.transaction_id == transaction_id,
            SplitTransaction.source == source,
        )
        return pd.read_sql(stmt, self.db.bind)

    def add_split(
        self, transaction_id: int, source: str, amount: float, category: str, tag: str
    ) -> int:
        """Add a new split for a transaction.

        Parameters
        ----------
        transaction_id : int
            Unique ID of the parent transaction.
        source : str
            Table name of the parent transaction's source (e.g. 'bank_transactions').
        amount : float
            Split amount. Negative values represent expenses.
        category : str or None
            Category to assign to this split.
        tag : str or None
            Tag to assign to this split.

        Returns
        -------
        int
            ID of the newly created split record.
        """
        split = SplitTransaction(
            transaction_id=transaction_id,
            source=source,
            amount=amount,
            category=category,
            tag=tag,
        )
        self.db.add(split)
        self.db.commit()
        return split.id

    def update_split(
        self, split_id: int, amount: float, category: str, tag: str
    ) -> None:
        """Update an existing split.

        Parameters
        ----------
        split_id : int
            Primary key of the split record to update.
        amount : float
            New split amount. Negative values represent expenses.
        category : str or None
            New category to assign.
        tag : str or None
            New tag to assign.
        """
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.id == split_id)
            .values(amount=amount, category=category, tag=tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_split(self, split_id: int) -> None:
        """Delete a split by ID.

        Parameters
        ----------
        split_id : int
            Primary key of the split record to delete.
        """
        stmt = delete(SplitTransaction).where(SplitTransaction.id == split_id)
        self.db.execute(stmt)
        self.db.commit()

    def delete_all_splits_for_transaction(
        self, transaction_id: int, source: str
    ) -> None:
        """Delete all splits for a specific transaction.

        Parameters
        ----------
        transaction_id : int
            Unique ID of the parent transaction.
        source : str
            Table name of the parent transaction's source.
        """
        stmt = delete(SplitTransaction).where(
            SplitTransaction.transaction_id == transaction_id,
            SplitTransaction.source == source,
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for matching splits.

        Parameters
        ----------
        category : str
            Category value to match against.
        tag : str
            Tag value to match against. Splits must match both category AND tag
            for their fields to be set to NULL.
        """
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == category)
            .where(SplitTransaction.tag == tag)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def update_category_for_tag(
        self, old_category: str, new_category: str, tag: str
    ) -> None:
        """Update category for splits with specified old_category and tag.

        Parameters
        ----------
        old_category : str
            Current category value to match against.
        new_category : str
            Replacement category value to assign.
        tag : str
            Tag value to filter by alongside old_category.
        """
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == old_category)
            .where(SplitTransaction.tag == tag)
            .values(category=new_category)
        )
        self.db.execute(stmt)
        self.db.commit()

    def rename_category(self, old_name: str, new_name: str) -> None:
        """Rename category across all split transactions."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == old_name)
            .values(category=new_name)
        )
        self.db.execute(stmt)
        self.db.commit()

    def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
        """Rename tag for split transactions with given category."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == category)
            .where(SplitTransaction.tag == old_tag)
            .values(tag=new_tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for splits with specified category.

        Parameters
        ----------
        category : str
            Category value to match against.

        Notes
        -----
        Also nullifies the tag field for all matching splits, not just the
        category field.
        """
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == category)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()
