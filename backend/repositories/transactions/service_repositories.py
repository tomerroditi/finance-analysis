"""
Per-table transaction repositories.

Defines the ``ServiceRepository`` base class (shared CRUD + tagging
operations against a single transaction table), the five concrete
per-table repositories, and the ``ManualTransactionDTO`` data class used
for manually inserted transactions.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Type

import pandas as pd
from sqlalchemy import cast, delete, func, Integer, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    InsuranceTransaction,
    ManualInvestmentTransaction,
    TransactionBase,
)
from backend.constants.tables import Tables

logger = logging.getLogger(__name__)

DEPOSIT_TYPE = "deposit"
WITHDRAWAL_TYPE = "withdrawal"


@dataclass
class ManualTransactionDTO:
    """Data class for manually inserted transactions (cash and manual investments)."""

    date: datetime
    account_name: str
    description: str
    amount: float
    transaction_type: Literal["deposit", "withdrawal"] | None = None
    provider: str | None = None
    account_number: str | None = None
    category: str | None = None
    tag: str | None = None


T_service = Literal[
    "credit_card",
    "bank",
    "cash",
    "manual_investments",
    "insurances",
    "credit_card_transactions",
    "bank_transactions",
    "cash_transactions",
    "manual_investment_transactions",
    "insurance_transactions",
]


class ServiceRepository:
    """
    Base class for service-specific transaction repositories using ORM.
    """

    model: Type[TransactionBase]

    unique_columns = ["id", "provider", "date", "amount"]

    def __init__(self, db: Session):
        """Initialize the repository with a database session.

        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def get_table(self) -> pd.DataFrame:
        """Get all transactions as a DataFrame.

        Returns
        -------
        pd.DataFrame
            All rows from this service's transaction table.
        """
        stmt = select(self.model)
        return pd.read_sql(stmt, self.db.bind)

    def update_tagging_by_unique_id(
        self, unique_id: int, category: str, tag: str
    ) -> None:
        """Update category and tag for a transaction by unique_id.

        Parameters
        ----------
        unique_id : int
            Transaction unique_id to update.
        category : str
            New category value (may be None to clear).
        tag : str
            New tag value (may be None to clear).
        """
        stmt = (
            update(self.model)
            .where(self.model.unique_id == int(unique_id))
            .values(category=category, tag=tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_transaction_by_unique_id(self, unique_id: int) -> bool:
        """Delete a transaction by its unique_id.

        Parameters
        ----------
        unique_id : int
            unique_id of the transaction to delete.

        Returns
        -------
        bool
            True if the transaction was deleted, False if not found.

        Raises
        ------
        SQLAlchemyError
            On database failure (after rollback) — not swallowed into the
            ``False`` return, which is reserved for "row not found".
        """
        try:
            stmt = delete(self.model).where(self.model.unique_id == int(unique_id))
            result = self.db.execute(stmt)
            self.db.commit()
            return result.rowcount > 0
        except SQLAlchemyError:
            logger.exception(
                "Delete failed for unique_id=%s in %s", unique_id, self.model.__tablename__
            )
            self.db.rollback()
            raise

    def update_transaction_by_unique_id(self, unique_id: int, updates: dict) -> bool:
        """Update arbitrary fields of a transaction by unique_id.

        Parameters
        ----------
        unique_id : int
            unique_id of the transaction to update.
        updates : dict
            Mapping of field names to new values. No-op if empty.

        Returns
        -------
        bool
            True if the transaction was updated, False if not found.

        Raises
        ------
        SQLAlchemyError
            On database failure (after rollback) — not swallowed into the
            ``False`` return, which is reserved for "row not found".
        """
        if not updates:
            return True

        try:
            stmt = (
                update(self.model)
                .where(self.model.unique_id == int(unique_id))
                .values(**updates)
            )
            result = self.db.execute(stmt)
            self.db.commit()
            return result.rowcount > 0
        except SQLAlchemyError:
            logger.exception(
                "Update failed for unique_id=%s in %s", unique_id, self.model.__tablename__
            )
            self.db.rollback()
            raise

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for all transactions with the given category.

        Parameters
        ----------
        category : str
            Category name to match.
        """
        stmt = (
            update(self.model)
            .where(self.model.category == category)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def update_category_for_tag(
        self, old_category: str, new_category: str, tag: str
    ) -> None:
        """Reassign category for all transactions with a specific category/tag pair.

        Parameters
        ----------
        old_category : str
            Current category to match.
        new_category : str
            New category to assign.
        tag : str
            Tag to match (only transactions with this tag are updated).
        """
        stmt = (
            update(self.model)
            .where(self.model.category == old_category)
            .where(self.model.tag == tag)
            .values(category=new_category)
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL for transactions matching both values.

        Parameters
        ----------
        category : str
            Category to match.
        tag : str
            Tag to match.
        """
        stmt = (
            update(self.model)
            .where(self.model.category == category)
            .where(self.model.tag == tag)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def rename_category(self, old_name: str, new_name: str) -> None:
        """Rename category across all transactions in this table."""
        stmt = (
            update(self.model)
            .where(self.model.category == old_name)
            .values(category=new_name)
        )
        self.db.execute(stmt)
        self.db.commit()

    def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
        """Rename tag for transactions with given category."""
        stmt = (
            update(self.model)
            .where(self.model.category == category)
            .where(self.model.tag == old_tag)
            .values(tag=new_tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def add_transaction(self, transaction: ManualTransactionDTO) -> bool:
        """Insert a manually created transaction into this service's table.

        Parameters
        ----------
        transaction : ManualTransactionDTO
            Data transfer object with all transaction fields.

        Returns
        -------
        bool
            True if successfully inserted, False on error.

        Notes
        -----
        Assigns a new id by incrementing the current maximum id in the table.
        """
        try:
            # id is stored as TEXT but contains number strings; cast to integer for MAX
            max_id = self.db.execute(
                select(func.max(cast(self.model.id, Integer)))
            ).scalar()

            new_id = str((int(max_id) + 1) if max_id is not None else 1)

            # Create model instance
            new_tx = self.model(
                date=transaction.date.strftime("%Y-%m-%d"),
                provider=transaction.provider,
                account_name=transaction.account_name,
                account_number=transaction.account_number,
                description=transaction.description,
                amount=transaction.amount,
                category=transaction.category,
                tag=transaction.tag,
                id=new_id,
                source=self.table,
            )

            self.db.add(new_tx)
            self.db.commit()
            return True
        except SQLAlchemyError:
            logger.exception(
                "Insert failed in %s", self.model.__tablename__
            )
            self.db.rollback()
            raise


class CreditCardRepository(ServiceRepository):
    model = CreditCardTransaction
    table = Tables.CREDIT_CARD.value

    def get_unique_accounts_tags(self) -> list:
        """Get unique account tag strings for all credit card accounts.

        Returns
        -------
        list[str]
            Strings in the format ``"provider - account_name - XXXX"`` where
            XXXX is the last 4 digits of the account number.  One entry per
            unique (provider, account_name, account_number) combination.
        """
        accounts = (
            self.db.query(
                self.model.provider, self.model.account_name, self.model.account_number
            )
            .distinct()
            .all()
        )
        accounts = [
            " - ".join([provider, account_name, (account_number or "")[-4:]])
            for (provider, account_name, account_number) in accounts
        ]
        return accounts


class BankRepository(ServiceRepository):
    model = BankTransaction
    table = Tables.BANK.value


class CashRepository(ServiceRepository):
    model = CashTransaction
    table = Tables.CASH.value


class ManualInvestmentTransactionsRepository(ServiceRepository):
    model = ManualInvestmentTransaction
    table = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value


class InsuranceRepository(ServiceRepository):
    model = InsuranceTransaction
    table = Tables.INSURANCE.value
