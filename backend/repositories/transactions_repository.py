"""
Transactions repository with SQLAlchemy ORM.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Type

import pandas as pd
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
    TransactionBase,
)
from backend.naming_conventions import Services, SplitTransactionsTableFields, Tables
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
        self.db = db

    def get_table(
        self, query: str | None = None, params: dict | None = None
    ) -> pd.DataFrame:
        """
        Get the transactions table as a DataFrame.
        """
        if query:
            # For backward compatibility with custom raw SQL queries
            result = self.db.execute(text(query), params or {})
            columns = result.keys()
            data = result.fetchall()
            return pd.DataFrame(data, columns=columns)
        else:
            stmt = select(self.model)
            # Use pandas read_sql to handle ORM objects easier or manual conversion
            # Using manual conversion to list of dicts to correctly handle model attributes
            # But read_sql with stmt and session.bind works great
            return pd.read_sql(stmt, self.db.bind)

    def update_with_query(self, query: str, query_params: dict | None = None) -> int:
        """
        Execute an UPDATE query and return the number of affected rows.
        Kept for backward compatibility/complex batch updates.
        """
        if not query.strip().lower().startswith("update"):
            raise ValueError("The query must be an UPDATE statement.")

        result = self.db.execute(text(query), query_params or {})
        self.db.commit()
        return result.rowcount

    def update_tagging_by_id(self, id_: str, category: str, tag: str) -> None:
        """Update category and tag for a transaction by ID."""
        # Note: id_ here expects the string ID column, not unique_id PK
        stmt = (
            update(self.model)
            .where(self.model.id == id_)
            .values(category=category, tag=tag)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_transaction_by_id(self, transaction_id: str) -> bool:
        """Delete a transaction by its unique_id."""
        try:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                f"Attempting to delete transaction_id={transaction_id} from table={self.model.__tablename__}"
            )
            stmt = delete(self.model).where(self.model.unique_id == int(transaction_id))
            result = self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Delete rowcount={result.rowcount}")
            return result.rowcount > 0
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Delete failed: {e}")
            self.db.rollback()
            return False

    def update_transaction_by_id(self, transaction_id: str, updates: dict) -> bool:
        """Update a transaction by its unique_id."""
        if not updates:
            return True

        try:
            stmt = (
                update(self.model)
                .where(self.model.unique_id == int(transaction_id))
                .values(**updates)
            )
            result = self.db.execute(stmt)
            self.db.commit()
            return result.rowcount > 0
        except Exception:
            self.db.rollback()
            return False

    def nullify_category(self, category: str) -> None:
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
        stmt = (
            update(self.model)
            .where(self.model.category == old_category)
            .where(self.model.tag == tag)
            .values(category=new_category)
        )
        self.db.execute(stmt)
        self.db.commit()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        stmt = (
            update(self.model)
            .where(self.model.category == category)
            .where(self.model.tag == tag)
            .values(category=None, tag=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def add_transaction(self, transaction: ManualTransactionDTO) -> bool:
        """Add a new transaction to the database."""
        # Calculate new ID (legacy string id logic)
        try:
            # Note: We need to cast id to integer for comparison to find the max
            # SQLite stores it as TEXT because of legacy schema, but they are number strings.
            # Using casting in SQL for max calculation.
            max_id = self.db.execute(
                text(f"SELECT MAX(CAST(id AS INTEGER)) FROM {self.table}")
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
        """get unique accounts according to provider, account name, and account number."""
        accounts = (
            self.db.query(
                self.model.provider, self.model.account_name, self.model.account_number
            )
            .distinct()
            .all()
        )
        accounts = [
            " - ".join([provider, account_name, account_number[-4:]])
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

    repo_map = {
        Tables.CREDIT_CARD.value: CreditCardRepository,
        Tables.BANK.value: BankRepository,
        Tables.CASH.value: CashRepository,
        Tables.MANUAL_INVESTMENT_TRANSACTIONS.value: ManualInvestmentTransactionsRepository,
        Services.CREDIT_CARD.value: CreditCardRepository,
        Services.BANK.value: BankRepository,
        Services.CASH.value: CashRepository,
        Services.MANUAL_INVESTMENTS.value: ManualInvestmentTransactionsRepository,
    }

    def __init__(self, db: Session):
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
        self.cash_repo = CashRepository(db)
        self.manual_investments_repo = ManualInvestmentTransactionsRepository(db)
        self.split_repo = SplitTransactionsRepository(db)

    def add_scraped_transactions(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Save scraped transactions avoiding duplicates.
        """
        if table_name not in self.tables:
            raise ValueError(f"table_name should be one of {self.tables}")

        repo_cls = self.repo_map.get(table_name)
        if not repo_cls:
            return

        # Instantiate repo to get model and props
        repo = repo_cls(self.db)
        model = repo.model

        # Using pandas for the merge logic as in original code is robust for the duplicate check
        stmt = select(model.id, model.provider, model.date, model.amount)
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
            instance = model(
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
        query: str | None = None,
        query_params: dict | None = None,
        include_split_parents: bool = False,
    ) -> pd.DataFrame:
        """Get transactions table with optional filtering and split handling."""
        df = self._get_base_transactions(service, query, query_params)

        if not include_split_parents:
            df = self._filter_split_parents(df)

        df = self._add_split_children(df, service)
        df = self._normalize_dates(df)

        return df

    def _get_base_transactions(
        self,
        service: T_service | None,
        query: str | None,
        query_params: dict | None,
    ) -> pd.DataFrame:
        """Fetch base transactions from repositories."""
        if service is not None:
            repo = self.get_repo_by_source(service)
            return repo.get_table(query, query_params)

        dfs = [
            self.cc_repo.get_table(query, query_params),
            self.bank_repo.get_table(query, query_params),
            self.cash_repo.get_table(query, query_params),
            self.manual_investments_repo.get_table(query, query_params),
        ]
        dfs = [df for df in dfs if not df.empty]

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    def _filter_split_parents(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove split parent transactions from the dataframe."""
        if df.empty or "type" not in df.columns:
            return df
        return df[df["type"] != "split_parent"]

    def _build_split_child(self, split: pd.Series) -> dict | None:
        """Build a split child row from a split record and its parent transaction."""
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

    def _get_split_children(self, service: T_service | None) -> pd.DataFrame:
        """Get all split children, optionally filtered by service."""
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

        return children_df

    def _add_split_children(
        self, df: pd.DataFrame, service: T_service | None
    ) -> pd.DataFrame:
        """Add split children to the transactions dataframe."""
        children_df = self._get_split_children(service)

        if children_df.empty:
            return df

        return pd.concat([df, children_df], ignore_index=True)

    def _normalize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize date column to YYYY-MM-DD format."""
        if df.empty or "date" not in df.columns:
            return df
        df["date"] = pd.to_datetime(df["date"]).dt.strftime(r"%Y-%m-%d")
        return df

    def split_transaction(
        self, unique_id: int, source: str, splits: list[dict]
    ) -> bool:
        try:
            repo = self.get_repo_by_source(source)
            repo.update_transaction_by_id(str(unique_id), {"type": "split_parent"})

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
        try:
            repo = self.get_repo_by_source(source)
            repo.update_transaction_by_id(str(unique_id), {"type": "normal"})

            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            return True
        except Exception:
            self.db.rollback()
            return False

    def get_repo_by_source(self, source: str) -> ServiceRepository:
        for key, repo_cls in self.repo_map.items():
            if source == key:
                # Need to return the instance, not class
                if isinstance(self.cc_repo, repo_cls):
                    return self.cc_repo
                if isinstance(self.bank_repo, repo_cls):
                    return self.bank_repo
                if isinstance(self.cash_repo, repo_cls):
                    return self.cash_repo
                if isinstance(self.manual_investments_repo, repo_cls):
                    return self.manual_investments_repo
        raise ValueError(f"Invalid source: '{source}'")

    def bulk_update_tagging(
        self, transactions: list[dict], category: Optional[str], tag: Optional[str]
    ) -> None:
        """
        Update tagging for multiple transactions.
        """
        for tx in transactions:
            self.update_tagging_by_id(tx["source"], tx["unique_id"], category, tag)

    def update_with_query(
        self,
        query: str,
        query_params: dict | None = None,
        service: T_service | None = None,
    ) -> int:
        """Execute an UPDATE query on the specified service(s)."""
        updated_rows = 0
        if service is None:
            updated_rows += self.cc_repo.update_with_query(query, query_params)
            updated_rows += self.bank_repo.update_with_query(query, query_params)
            updated_rows += self.cash_repo.update_with_query(query, query_params)
            updated_rows += self.manual_investments_repo.update_with_query(
                query, query_params
            )
        else:
            repo = self.get_repo_by_source(service)
            updated_rows += repo.update_with_query(query, query_params)
        return updated_rows

    def get_latest_date_from_table(self, table_name: str) -> datetime | None:
        repo_cls = self.repo_map.get(table_name)
        if not repo_cls:
            return None

        # We need an instance to get the model usually, but class is enough here
        model = repo_cls.model
        result = self.db.execute(
            select(model.date).order_by(model.date.desc()).limit(1)
        ).scalar()

        if result is not None:
            try:
                return datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                return None
        return None

    def get_earliest_date_from_table(self, table_name: str) -> datetime | None:
        repo_cls = self.repo_map.get(table_name)
        if not repo_cls:
            return None

        model = repo_cls.model
        result = self.db.execute(
            select(model.date).order_by(model.date.asc()).limit(1)
        ).scalar()

        if result is not None:
            try:
                return datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                return None
        return None

    def get_all_table_names(self) -> list[str]:
        return self.tables.copy()

    def nullify_category_and_tag(self, category: str, tag: str) -> None:
        self.cc_repo.nullify_category_and_tag(category, tag)
        self.bank_repo.nullify_category_and_tag(category, tag)
        self.cash_repo.nullify_category_and_tag(category, tag)
        self.manual_investments_repo.nullify_category_and_tag(category, tag)

    def update_category_for_tag(
        self, old_category: str, new_category: str, tag: str
    ) -> None:
        self.cc_repo.update_category_for_tag(old_category, new_category, tag)
        self.bank_repo.update_category_for_tag(old_category, new_category, tag)
        self.cash_repo.update_category_for_tag(old_category, new_category, tag)
        self.manual_investments_repo.update_category_for_tag(
            old_category, new_category, tag
        )

    def nullify_category(self, category: str) -> None:
        self.cc_repo.nullify_category(category)
        self.bank_repo.nullify_category(category)
        self.cash_repo.nullify_category(category)
        self.manual_investments_repo.nullify_category(category)

    def get_transaction_by_id(self, transaction_id: int) -> pd.Series:
        df = self.get_table()
        transaction = df[df["unique_id"] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found.")
        elif len(transaction) > 1:
            raise ValueError(f"Multiple transactions found with ID {transaction_id}.")
        return transaction.iloc[0]
