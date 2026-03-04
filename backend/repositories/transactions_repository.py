"""
Transactions repository with SQLAlchemy ORM.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Type

import pandas as pd
from sqlalchemy import cast, delete, func, Integer, select, update
from sqlalchemy.orm import Session

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
    TransactionBase,
)
from backend.constants.providers import Services
from backend.constants.tables import SplitTransactionsTableFields, Tables
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)

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
    "credit_card_transactions",
    "bank_transactions",
    "cash_transactions",
    "manual_investment_transactions",
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
            True if the transaction was deleted, False if not found or on error.
        """
        try:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                f"Attempting to delete unique_id={unique_id} from table={self.model.__tablename__}"
            )
            stmt = delete(self.model).where(self.model.unique_id == int(unique_id))
            result = self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Delete rowcount={result.rowcount}")
            return result.rowcount > 0
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Delete failed: {e}")
            self.db.rollback()
            return False

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
            True if the transaction was updated, False if not found or on error.
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
        except Exception:
            self.db.rollback()
            return False

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
        except Exception:
            self.db.rollback()
            return False


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


class TransactionsRepository:
    """
    Main repository aggregating all transaction types.
    """

    tables = [
        Tables.CREDIT_CARD.value,
        Tables.BANK.value,
        Tables.CASH.value,
        Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
    ]

    unique_columns = ["id", "provider", "date", "amount"]

    def __init__(self, db: Session):
        """Initialize the repository with sub-repositories for each transaction type.

        Parameters
        ----------
        db : Session
            SQLAlchemy database session shared across all sub-repositories.

        Notes
        -----
        Builds a ``repo_map`` keyed by both table name and service name variants
        (e.g. ``"credit_card_transactions"`` and ``"credit_card"``) to support
        flexible source-based dispatch.
        """
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
        self.cash_repo = CashRepository(db)
        self.manual_investments_repo = ManualInvestmentTransactionsRepository(db)
        self.split_repo = SplitTransactionsRepository(db)

        self.repo_map = {
            Tables.CREDIT_CARD.value: self.cc_repo,
            Tables.BANK.value: self.bank_repo,
            Tables.CASH.value: self.cash_repo,
            Tables.MANUAL_INVESTMENT_TRANSACTIONS.value: self.manual_investments_repo,
            Services.CREDIT_CARD.value: self.cc_repo,
            Services.BANK.value: self.bank_repo,
            Services.CASH.value: self.cash_repo,
            Services.MANUAL_INVESTMENTS.value: self.manual_investments_repo,
        }

    def add_scraped_transactions(self, df: pd.DataFrame, table_name: str) -> None:
        """Persist scraped transactions, skipping rows that already exist.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame of scraped transactions to insert.  Must contain columns:
            id, provider, date, amount plus any other transaction fields.
        table_name : str
            Target table name; must be one of the four supported tables.

        Raises
        ------
        ValueError
            If ``table_name`` is not in the list of supported tables.

        Notes
        -----
        Deduplication is based on the composite key (id, provider, date, amount).
        Only rows not already present in the DB are inserted.
        """
        if table_name not in self.tables:
            raise ValueError(f"table_name should be one of {self.tables}")

        repo = self.get_repo_by_source(table_name)

        # Using pandas for the merge logic as in original code is robust for the duplicate check
        stmt = select(
            repo.model.id, repo.model.provider, repo.model.date, repo.model.amount
        )
        existing_data = pd.read_sql(stmt, self.db.bind)

        # Make sure columns align for merge
        df = df.astype({col: str for col in self.unique_columns})
        existing_data = existing_data.astype({col: str for col in self.unique_columns})

        if not existing_data.empty:
            merged_df = df.merge(
                existing_data, on=self.unique_columns, how="left", indicator=True
            )
            new_rows = merged_df[merged_df["_merge"] == "left_only"].drop(
                columns="_merge"
            )
        else:
            new_rows = df

        if new_rows.empty:
            return

        # Prepare list of model instances
        instances = []
        for _, row in new_rows.iterrows():
            instance = repo.model(
                id=row["id"],
                date=row["date"],
                provider=row["provider"],
                account_name=row["account_name"],
                account_number=row.get("account_number"),
                description=row.get("description"),
                amount=float(row["amount"]),
                category=row.get("category"),
                tag=row.get("tag"),
                source=row.get("source", repo.table),
                type=row.get("type", "normal"),
                status=row.get("status", "completed"),
            )
            instances.append(instance)

        self.db.add_all(instances)
        self.db.commit()

    def add_transaction(
        self,
        transaction: ManualTransactionDTO,
        service: str,
    ) -> bool:
        """Add a manually created transaction to the appropriate sub-repository.

        Parameters
        ----------
        transaction : ManualTransactionDTO
            Data transfer object with all transaction fields.
        service : str
            Target service; must be ``"cash"`` or ``"manual_investments"``.

        Returns
        -------
        bool
            True if successfully inserted.

        Raises
        ------
        ValueError
            If ``service`` is not ``"cash"`` or ``"manual_investments"``.
        """
        if service == Services.CASH.value:
            return self.cash_repo.add_transaction(transaction)
        elif service == Services.MANUAL_INVESTMENTS.value:
            return self.manual_investments_repo.add_transaction(transaction)
        else:
            raise ValueError(
                f"service must be 'cash' or 'manual_investments'. Got '{service}'"
            )

    def get_table(
        self,
        service: T_service | None = None,
        include_split_parents: bool = False,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Get transactions table with optional filtering and split handling.

        Parameters
        ----------
        service : T_service | None
            If provided, return only transactions from this service.
        include_split_parents : bool
            If True, keep split-parent rows in the result.
        exclude_services : list[T_service] | None
            When fetching all services (``service=None``), skip these services.
            Ignored when ``service`` is specified.

        Returns
        -------
        pd.DataFrame
            Combined transactions from all requested sources.  Split parents are
            replaced by their split children (type ``"split_child"``) unless
            ``include_split_parents=True``.  Date column is normalized to
            ``YYYY-MM-DD`` string format.
        """
        df = self._get_base_transactions(service, exclude_services)

        if not include_split_parents:
            df = self._filter_split_parents(df)

        df = self._add_split_children(df, service, exclude_services)
        df = self._normalize_dates(df)

        return df

    def _get_base_transactions(
        self,
        service: T_service | None,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Fetch raw transactions from the appropriate repositories.

        Parameters
        ----------
        service : T_service | None
            If provided, fetch only from that service's repository.
            If None, fetch from all repositories minus any exclusions.
        exclude_services : list[T_service] | None
            Services to skip when fetching all (ignored when service is given).

        Returns
        -------
        pd.DataFrame
            Concatenated transactions; empty DataFrame if no data found.
        """
        if service is not None:
            repo = self.get_repo_by_source(service)
            return repo.get_table()

        excluded_repos = {
            repo
            for s in (exclude_services or [])
            if (repo := self.get_repo_by_source(s)) is not None
        }

        all_repos = [
            self.cc_repo,
            self.bank_repo,
            self.cash_repo,
            self.manual_investments_repo,
        ]
        dfs = [
            repo.get_table()
            for repo in all_repos
            if repo not in excluded_repos
        ]
        dfs = [df for df in dfs if not df.empty]

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    def _filter_split_parents(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows where type is ``"split_parent"`` from the DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Input transactions DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with split_parent rows removed.
        """
        if df.empty or "type" not in df.columns:
            return df
        return df[df["type"] != "split_parent"]

    def _build_split_child(self, split: pd.Series) -> dict | None:
        """Construct a split-child row dict from a split record and its parent.

        Parameters
        ----------
        split : pd.Series
            A row from the split_transactions table.

        Returns
        -------
        dict | None
            Row dict with parent transaction fields overridden by split-specific
            values (unique_id, amount, category, tag, type="split_child").
            Returns None if the parent transaction cannot be found.
        """
        parent_id = split[SplitTransactionsTableFields.TRANSACTION_ID.value]
        source = split[SplitTransactionsTableFields.SOURCE.value]

        try:
            repo = self.get_repo_by_source(source)
            parent = self.db.execute(
                select(repo.model).where(repo.model.unique_id == int(parent_id))
            ).scalar_one_or_none()

            if not parent:
                return None

            parent_dict = {
                c.name: getattr(parent, c.name) for c in parent.__table__.columns
            }

            return {
                **parent_dict,
                "unique_id": f"split_{split[SplitTransactionsTableFields.ID.value]}",
                "amount": split[SplitTransactionsTableFields.AMOUNT.value],
                "category": split[SplitTransactionsTableFields.CATEGORY.value],
                "tag": split[SplitTransactionsTableFields.TAG.value],
                "type": "split_child",
                "source": source,
            }
        except Exception:
            return None

    def _get_split_children(
        self,
        service: T_service | None,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Build split-child rows for all splits, filtered by service if given.

        Parameters
        ----------
        service : T_service | None
            If provided, include only splits whose source maps to this service.
        exclude_services : list[T_service] | None
            If provided, exclude splits whose source maps to any of these services.

        Returns
        -------
        pd.DataFrame
            DataFrame of split-child rows; empty if no splits exist or all filtered.
        """
        splits_df = self.split_repo.get_data()

        if splits_df.empty:
            return pd.DataFrame()

        children = []
        for _, split in splits_df.iterrows():
            child = self._build_split_child(split)
            if child:
                children.append(child)

        if not children:
            return pd.DataFrame()

        children_df = pd.DataFrame(children)

        if service:
            target_repo = self.get_repo_by_source(service)
            valid_sources = [
                src
                for src in children_df["source"].unique()
                if self.get_repo_by_source(src) == target_repo
            ]
            children_df = children_df[children_df["source"].isin(valid_sources)]
        elif exclude_services:
            excluded_repos = {
                repo
                for s in exclude_services
                if (repo := self.get_repo_by_source(s)) is not None
            }
            excluded_sources = [
                src
                for src in children_df["source"].unique()
                if self.get_repo_by_source(src) in excluded_repos
            ]
            children_df = children_df[~children_df["source"].isin(excluded_sources)]

        return children_df

    def _add_split_children(
        self,
        df: pd.DataFrame,
        service: T_service | None,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Concatenate split-child rows onto the transactions DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Base transactions DataFrame (with split parents already filtered).
        service : T_service | None
            Passed through to ``_get_split_children`` for filtering.
        exclude_services : list[T_service] | None
            Passed through to ``_get_split_children`` for filtering.

        Returns
        -------
        pd.DataFrame
            DataFrame with split children appended; original df if none exist.
        """
        children_df = self._get_split_children(service, exclude_services)

        if children_df.empty:
            return df

        return pd.concat([df, children_df], ignore_index=True)

    def _normalize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert the date column to consistent YYYY-MM-DD string format.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing a ``date`` column.

        Returns
        -------
        pd.DataFrame
            Same DataFrame with ``date`` column cast to ``"%Y-%m-%d"`` strings.
            Returns df unchanged if empty or if ``date`` column is absent.
        """
        if df.empty or "date" not in df.columns:
            return df
        df["date"] = pd.to_datetime(df["date"]).dt.strftime(r"%Y-%m-%d")
        return df

    def split_transaction(
        self, unique_id: int, source: str, splits: list[dict]
    ) -> bool:
        """Split a transaction into multiple partial amounts across categories.

        Parameters
        ----------
        unique_id : int
            unique_id of the transaction to split.
        source : str
            Table name of the source repository.
        splits : list[dict]
            List of split dicts, each with keys: amount, category, tag.

        Returns
        -------
        bool
            True if the split was committed successfully, False on error
            (rolls back the transaction in that case).

        Notes
        -----
        Marks the original transaction as type ``"split_parent"`` and creates
        one split_transaction record per element in ``splits``.  Any existing
        splits for this transaction are replaced.
        """
        try:
            repo = self.get_repo_by_source(source)
            repo.update_transaction_by_unique_id(
                str(unique_id), {"type": "split_parent"}
            )

            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            for split in splits:
                self.split_repo.add_split(
                    transaction_id=unique_id,
                    source=source,
                    amount=split["amount"],
                    category=split["category"],
                    tag=split["tag"],
                )
            return True
        except Exception:
            self.db.rollback()
            return False

    def revert_split(self, unique_id: int, source: str) -> bool:
        """Revert a split transaction back to a normal transaction.

        Parameters
        ----------
        unique_id : int
            unique_id of the split-parent transaction to revert.
        source : str
            Table name of the source repository.

        Returns
        -------
        bool
            True if reverted successfully, False on error.

        Notes
        -----
        Sets the transaction type back to ``"normal"`` and deletes all associated
        split_transaction records.
        """
        try:
            repo = self.get_repo_by_source(source)
            repo.update_transaction_by_unique_id(str(unique_id), {"type": "normal"})

            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            return True
        except Exception:
            self.db.rollback()
            return False

    def get_repo_by_source(self, source: str) -> ServiceRepository:
        """Look up the sub-repository for a given source/service name.

        Parameters
        ----------
        source : str
            Table name or service name (e.g. ``"credit_card_transactions"`` or
            ``"credit_card"``).

        Returns
        -------
        ServiceRepository
            The matching sub-repository instance.

        Raises
        ------
        ValueError
            If ``source`` is not a recognized key in the repo_map.
        """
        try:
            return self.repo_map.get(source)
        except Exception:
            raise ValueError(f"Invalid source: '{source}'")

    def bulk_update_tagging(
        self, transactions: list[dict], category: Optional[str], tag: Optional[str]
    ) -> None:
        """Update category and tag for a batch of transactions.

        Parameters
        ----------
        transactions : list[dict]
            Each dict must have keys ``"source"`` (table name) and
            ``"unique_id"`` identifying the transaction to update.
        category : str | None
            New category to assign (None clears the field).
        tag : str | None
            New tag to assign (None clears the field).
        """
        for tx in transactions:
            repo = self.get_repo_by_source(tx["source"])
            repo.update_tagging_by_unique_id(tx["unique_id"], category, tag)

    def get_latest_date_from_table(self, table_name: str) -> datetime | None:
        """Get the most recent transaction date in a given table.

        Parameters
        ----------
        table_name : str
            Source table name to query.

        Returns
        -------
        datetime | None
            Latest transaction date parsed from ``YYYY-MM-DD``, or None if
            the table is empty or the date cannot be parsed.
        """
        repo = self.get_repo_by_source(table_name)
        result = self.db.execute(
            select(repo.model.date).order_by(repo.model.date.desc()).limit(1)
        ).scalar()

        if result is not None:
            try:
                return datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                return None
        return None

    def get_earliest_date_from_table(self, table_name: str) -> datetime | None:
        """Get the earliest transaction date in a given table.

        Parameters
        ----------
        table_name : str
            Source table name to query.

        Returns
        -------
        datetime | None
            Earliest transaction date parsed from ``YYYY-MM-DD``, or None if
            the table is empty or the date cannot be parsed.
        """
        repo = self.get_repo_by_source(table_name)
        result = self.db.execute(
            select(repo.model.date).order_by(repo.model.date.asc()).limit(1)
        ).scalar()

        if result is not None:
            try:
                return datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                return None
        return None

    def get_all_table_names(self) -> list[str]:
        """Return the list of all transaction table names.

        Returns
        -------
        list[str]
            Copy of the class-level ``tables`` list containing the four
            transaction table name strings.
        """
        return self.tables.copy()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        """Set category and tag to NULL across all transaction tables.

        Parameters
        ----------
        category : str
            Category to match.
        tag : str
            Tag to match.

        Notes
        -----
        Delegates to all four sub-repositories (credit card, bank, cash,
        manual investments).
        """
        self.cc_repo.nullify_category_and_tag(category, tag)
        self.bank_repo.nullify_category_and_tag(category, tag)
        self.cash_repo.nullify_category_and_tag(category, tag)
        self.manual_investments_repo.nullify_category_and_tag(category, tag)

    def update_category_for_tag(
        self, old_category: str, new_category: str, tag: str
    ) -> None:
        """Update category for a specific tag across all transaction tables.

        Parameters
        ----------
        old_category : str
            Current category to match.
        new_category : str
            New category to assign.
        tag : str
            Tag to match.

        Notes
        -----
        Delegates to all four sub-repositories.
        """
        self.cc_repo.update_category_for_tag(old_category, new_category, tag)
        self.bank_repo.update_category_for_tag(old_category, new_category, tag)
        self.cash_repo.update_category_for_tag(old_category, new_category, tag)
        self.manual_investments_repo.update_category_for_tag(
            old_category, new_category, tag
        )

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for all transactions in a category.

        Parameters
        ----------
        category : str
            Category name to clear across all transaction tables.

        Notes
        -----
        Delegates to all four sub-repositories.
        """
        self.cc_repo.nullify_category(category)
        self.bank_repo.nullify_category(category)
        self.cash_repo.nullify_category(category)
        self.manual_investments_repo.nullify_category(category)

    def get_transaction_by_id(self, transaction_id: int) -> pd.Series:
        """Retrieve a single transaction row by its unique_id.

        Parameters
        ----------
        transaction_id : int
            The unique_id to look up.

        Returns
        -------
        pd.Series
            The matching transaction row.

        Raises
        ------
        ValueError
            If no transaction with that unique_id is found, or if multiple rows
            match (which should not happen in practice).
        """
        df = self.get_table()
        transaction = df[df["unique_id"] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found.")
        elif len(transaction) > 1:
            raise ValueError(f"Multiple transactions found with ID {transaction_id}.")
        return transaction.iloc[0]
