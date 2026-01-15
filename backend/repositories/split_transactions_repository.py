"""
Split transactions repository with SQLAlchemy ORM.
"""
import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.models.transaction import SplitTransaction
from backend.naming_conventions import Tables, SplitTransactionsTableFields


class SplitTransactionsRepository:
    """
    Repository for managing split transaction records using ORM.
    """
    def __init__(self, db: Session):
        self.db = db

    def _assure_table_exists(self) -> None:
        pass

    def get_data(self) -> pd.DataFrame:
        """Get all split transactions."""
        stmt = select(SplitTransaction)
        return pd.read_sql(stmt, self.db.bind)

    def get_splits_for_transaction(self, transaction_id: int, source: str) -> pd.DataFrame:
        """Get all splits for a specific transaction."""
        stmt = select(SplitTransaction).where(
            SplitTransaction.transaction_id == transaction_id,
            SplitTransaction.source == source
        )
        return pd.read_sql(stmt, self.db.bind)

    def add_split(self, transaction_id: int, source: str, amount: float, category: str, tag: str) -> int:
        """
        Add a new split for a transaction.
        Returns the ID of the newly created split.
        """
        split = SplitTransaction(
            transaction_id=transaction_id,
            source=source,
            amount=amount,
            category=category,
            tag=tag
        )
        self.db.add(split)
        self.db.commit()
        return split.id

    def update_split(self, split_id: int, amount: float, category: str, tag: str) -> None:
        """Update an existing split."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.id == split_id)
            .values(amount=amount, category=category, tag=tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_split(self, split_id: int) -> None:
        """Delete a split by ID."""
        stmt = delete(SplitTransaction).where(SplitTransaction.id == split_id)
        self.db.execute(stmt)
        self.db.commit()

    def delete_all_splits_for_transaction(self, transaction_id: int, source: str) -> None:
        """Delete all splits for a specific transaction."""
        stmt = delete(SplitTransaction).where(
            SplitTransaction.transaction_id == transaction_id,
            SplitTransaction.source == source
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for matching splits."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == category)
            .where(SplitTransaction.tag == tag)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def update_category_for_tag(self, old_category: str, new_category: str, tag: str) -> None:
        """Update category for splits with specified old_category and tag."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == old_category)
            .where(SplitTransaction.tag == tag)
            .values(category=new_category)
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for splits with specified category."""
        stmt = (
            update(SplitTransaction)
            .where(SplitTransaction.category == category)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()
