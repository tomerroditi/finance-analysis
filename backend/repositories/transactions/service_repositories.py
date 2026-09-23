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
from typing import Any, ClassVar, Literal

import pandas as pd
from sqlalchemy import Integer, cast, delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.constants.tables import Tables, table_aliases
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    InsuranceTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
    TransactionBase,
)

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
    """Base class for service-specific transaction repositories using ORM."""

    model: type[TransactionBase]
    table: str

    unique_columns: ClassVar[list[str]] = ["id", "provider", "date", "amount"]

    def __init__(self, db: Session) -> None:
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

    def sum_amount(
        self,
        account_name: str | None,
        provider: str | None = None,
        *,
        expand_splits: bool = False,
    ) -> float:
        """Sum the amounts of one account's transactions in this table.

        Parameters
        ----------
        account_name : str or None
            Account name to match exactly; ``None`` matches no row.
        provider : str or None, optional
            When given, only rows of this provider count.
        expand_splits : bool, optional
            When ``True``, sum the account as the merged transactions view
            shows it: ``split_parent`` rows are replaced by their split
            slices (slices whose parent row is gone are dropped). When
            ``False`` (default), every stored row counts as is.

        Returns
        -------
        float
            The total; ``0.0`` when nothing matches. NULL amounts are skipped.
        """
        if account_name is None:
            return 0.0
        filters = [self.model.account_name == account_name]
        if provider is not None:
            filters.append(self.model.provider == provider)

        if not expand_splits:
            stmt = select(func.sum(self.model.amount)).where(*filters)
            return float(self.db.execute(stmt).scalar() or 0.0)

        direct = select(func.sum(self.model.amount)).where(
            *filters,
            or_(self.model.type.is_(None), self.model.type != "split_parent"),
        )
        slices = (
            select(func.sum(SplitTransaction.amount))
            .join(self.model, self.model.unique_id == SplitTransaction.transaction_id)
            .where(SplitTransaction.source.in_(table_aliases(self.table)), *filters)
        )
        return float(self.db.execute(direct).scalar() or 0.0) + float(
            self.db.execute(slices).scalar() or 0.0
        )

    def update_tagging_by_unique_id(
        self, unique_id: int, category: str | None, tag: str | None
    ) -> None:
        """Update category and tag for a transaction by unique_id.

        Parameters
        ----------
        unique_id : int
            Transaction unique_id to update.
        category : str or None
            New category value (None clears it).
        tag : str or None
            New tag value (None clears it).
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
                "Delete failed for unique_id=%s in %s",
                unique_id,
                self.model.__tablename__,
            )
            self.db.rollback()
            raise

    def get_unique_ids_for_account(self, provider: str, account_name: str) -> list[int]:
        """List the unique_ids of every transaction belonging to one account.

        Parameters
        ----------
        provider : str
            Provider identifier (e.g. ``"hapoalim"``).
        account_name : str
            Account name as stored on the transactions.

        Returns
        -------
        list[int]
            unique_ids in this repository's table for that account.
        """
        stmt = select(self.model.unique_id).where(
            self.model.provider == provider,
            self.model.account_name == account_name,
        )
        return [row[0] for row in self.db.execute(stmt).all()]

    def delete_transactions_for_account(self, provider: str, account_name: str) -> int:
        """Delete every transaction belonging to one account.

        The caller is responsible for purging records that reference these
        rows first — see ``TransactionsService.delete_account_data``.

        Parameters
        ----------
        provider : str
            Provider identifier.
        account_name : str
            Account name as stored on the transactions.

        Returns
        -------
        int
            Number of transactions deleted.

        Raises
        ------
        SQLAlchemyError
            On database failure, after rolling back.
        """
        try:
            stmt = delete(self.model).where(
                self.model.provider == provider,
                self.model.account_name == account_name,
            )
            result = self.db.execute(stmt)
            self.db.commit()
            return result.rowcount
        except SQLAlchemyError:
            logger.exception(
                "Account delete failed for %s/%s in %s",
                provider,
                account_name,
                self.model.__tablename__,
            )
            self.db.rollback()
            raise

    def update_transaction_by_unique_id(
        self, unique_id: int, updates: dict[str, Any]
    ) -> bool:
        """Update arbitrary fields of a transaction by unique_id.

        Parameters
        ----------
        unique_id : int
            unique_id of the transaction to update.
        updates : dict[str, Any]
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
                "Update failed for unique_id=%s in %s",
                unique_id,
                self.model.__tablename__,
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
            True once the row is inserted.

        Raises
        ------
        SQLAlchemyError
            On database failure, after rolling back.

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
            logger.exception("Insert failed in %s", self.model.__tablename__)
            self.db.rollback()
            raise


class CreditCardRepository(ServiceRepository):
    """Transactions in the ``credit_card_transactions`` table."""

    model = CreditCardTransaction
    table = Tables.CREDIT_CARD.value

    def get_unique_accounts_tags(self) -> list[str]:
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
        return [
            " - ".join([provider, account_name, (account_number or "")[-4:]])
            for (provider, account_name, account_number) in accounts
        ]


class BankRepository(ServiceRepository):
    """Transactions in the ``bank_transactions`` table."""

    model = BankTransaction
    table = Tables.BANK.value


class CashRepository(ServiceRepository):
    """Transactions in the ``cash_transactions`` table."""

    model = CashTransaction
    table = Tables.CASH.value

    def delete_by_account_and_tag(self, account_name: str, tag: str) -> None:
        """Delete every cash transaction of one account carrying one tag.

        Parameters
        ----------
        account_name : str
            Account name to match.
        tag : str
            Tag to match.
        """
        self.db.execute(
            delete(self.model).where(
                self.model.tag == tag, self.model.account_name == account_name
            )
        )
        self.db.commit()

    def rename_account(self, old_name: str, new_name: str) -> None:
        """Move every cash transaction of one account to another account name.

        Parameters
        ----------
        old_name : str
            Current account name.
        new_name : str
            Account name to assign.
        """
        self.db.execute(
            update(self.model)
            .where(self.model.account_name == old_name)
            .values(account_name=new_name)
        )
        self.db.commit()


class ManualInvestmentTransactionsRepository(ServiceRepository):
    """Transactions in the ``manual_investment_transactions`` table."""

    model = ManualInvestmentTransaction
    table = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value


class InsuranceRepository(ServiceRepository):
    """Transactions in the ``insurance_transactions`` table.

    Insurance transactions key their policy by ``account_number``.
    """

    model = InsuranceTransaction
    table = Tables.INSURANCE.value

    def get_latest_for_policy(self, policy_id: str) -> InsuranceTransaction | None:
        """Return a policy's most recent transaction.

        Parameters
        ----------
        policy_id : str
            Policy identifier, stored as the transaction's ``account_number``.

        Returns
        -------
        InsuranceTransaction or None
            The row with the latest ``date``, or ``None`` when the policy has
            no transactions.
        """
        stmt = (
            select(self.model)
            .where(self.model.account_number == policy_id)
            .order_by(self.model.date.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def get_first_dates(self, policy_ids: list[str]) -> dict[str, str | None]:
        """Return each policy's earliest transaction date.

        Parameters
        ----------
        policy_ids : list[str]
            Policy identifiers, stored as the transactions' ``account_number``.

        Returns
        -------
        dict[str, str or None]
            Policy id to its minimum stored ``date``; policies without
            transactions are absent.
        """
        if not policy_ids:
            return {}
        stmt = (
            select(self.model.account_number, func.min(self.model.date))
            .where(self.model.account_number.in_(policy_ids))
            .group_by(self.model.account_number)
        )
        return dict(self.db.execute(stmt).tuples().all())

    def get_for_policy(self, policy_id: str) -> pd.DataFrame:
        """Return every transaction of one policy.

        Parameters
        ----------
        policy_id : str
            Policy identifier, stored as the transactions' ``account_number``.

        Returns
        -------
        pd.DataFrame
            The policy's rows with all table columns (empty when none).
        """
        stmt = select(self.model).where(self.model.account_number == policy_id)
        return pd.read_sql(stmt, self.db.bind)
