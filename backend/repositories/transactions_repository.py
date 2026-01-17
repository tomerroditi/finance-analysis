"""
Transactions repository with SQLAlchemy ORM.
"""

from datetime import datetime
from typing import Literal, Optional, Type
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select, update, delete, text
from sqlalchemy.orm import Session

from backend.models.transaction import (
    TransactionBase,
    BankTransaction,
    CreditCardTransaction,
    CashTransaction,
    ManualInvestmentTransaction,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.naming_conventions import (
    Tables,
    CreditCardTableFields,
    BankTableFields,
    CashTableFields,
    TransactionsTableFields,
    Services,
    ManualInvestmentTransactionsTableFields,
)


DEPOSIT_TYPE = "deposit"
WITHDRAWAL_TYPE = "withdrawal"


@dataclass
class CashTransactionDTO:
    """Data class representing a cash transaction."""

    date: datetime
    account_name: str
    desc: str
    amount: float
    provider: str | None = None
    account_number: str | None = None
    category: str | None = None
    tag: str | None = None


@dataclass
class ManualInvestmentTransactionDTO:
    """Data class representing a manual investment transaction."""

    date: datetime
    account_name: str
    desc: str
    amount: float
    transaction_type: Literal["deposit", "withdrawal"]
    provider: str
    account_number: str
    category: str
    tag: str


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
            stmt = delete(self.model).where(self.model.unique_id == int(transaction_id))
            result = self.db.execute(stmt)
            self.db.commit()
            return result.rowcount > 0
        except Exception:
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

    def add_transaction(
        self, transaction: CashTransactionDTO | ManualInvestmentTransactionDTO
    ) -> bool:
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
                desc=transaction.desc,
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


class BankRepository(ServiceRepository):
    model = BankTransaction
    table = Tables.BANK.value


class CashRepository(ServiceRepository):
    model = CashTransaction
    table = Tables.CASH.value


class ManualInvestmentTransactionsRepository(CashRepository):
    model = ManualInvestmentTransaction
    table = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value

    def add_transaction(self, transaction: ManualInvestmentTransactionDTO) -> bool:
        """Add a manual investment transaction (deposits are negative amounts)."""
        # Logic specific to manual investments sign handling
        amount = (
            transaction.amount * -1
            if transaction.transaction_type == DEPOSIT_TYPE
            else transaction.amount
        )

        # Create a new DTO/object with adjusted amount to pass to super or handle directly
        # We need to make a copy to avoid side effects if the original DTO is used elsewhere
        tx_copy = ManualInvestmentTransactionDTO(
            date=transaction.date,
            account_name=transaction.account_name,
            desc=transaction.desc,
            amount=amount,
            transaction_type=transaction.transaction_type,
            provider=transaction.provider,
            account_number=transaction.account_number,
            category=transaction.category,
            tag=transaction.tag,
        )
        return super().add_transaction(tx_copy)


class TransactionsRepository:
    """
    Main repository aggregating all transaction types.
    """

    tables = [Tables.CREDIT_CARD.value, Tables.BANK.value, Tables.CASH.value]

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
                desc=row.get("desc"),
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
        transaction: CashTransactionDTO | ManualInvestmentTransactionDTO,
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
        if service is None:
            dfs = [
                self.cc_repo.get_table(query, query_params),
                self.bank_repo.get_table(query, query_params),
                self.cash_repo.get_table(query, query_params),
                self.manual_investments_repo.get_table(query, query_params),
            ]
            dfs = [df for df in dfs if not df.empty]
            if not dfs:
                return pd.DataFrame()
            df = pd.concat(dfs, ignore_index=True)
        else:
            repo = self.get_repo_by_source(service)
            df = repo.get_table(query, query_params)

        if not include_split_parents and not df.empty and "type" in df.columns:
            df = df[df["type"] != "split_parent"]

        # Add split children
        # Note: We need to refactor split repo to ORM first to fully utilize ORM here,
        # but existing split repo uses SQL. Converting df logic is same.
        # Ideally, we should fetch splits via relationship or updated split repo logic.
        # For now, using existing logic but adapting to use get_repo_by_source which now returns ORM repos.

        splits_df = (
            self.split_repo.get_data()
        )  # This relies on split_repo still working (it is raw SQL currently)
        if not splits_df.empty:
            children = []
            for _, split in splits_df.iterrows():
                parent_id = split[self.split_repo.transaction_id_col]
                source = split[self.split_repo.source_col]

                try:
                    repo = self.get_repo_by_source(source)
                    # Use ORM to fetch parent
                    parent = self.db.execute(
                        select(repo.model).where(repo.model.unique_id == int(parent_id))
                    ).scalar_one_or_none()

                    if parent:
                        # Convert parent model to dict
                        parent_dict = {
                            c.name: getattr(parent, c.name)
                            for c in parent.__table__.columns
                        }

                        child = parent_dict.copy()
                        child["unique_id"] = f"split_{split[self.split_repo.id_col]}"
                        child["amount"] = split[self.split_repo.amount_col]
                        child["category"] = split[self.split_repo.category_col]
                        child["tag"] = split[self.split_repo.tag_col]
                        child["type"] = "split_child"
                        child["source"] = source
                        children.append(child)
                except Exception:
                    continue

            if children:
                children_df = pd.DataFrame(children)
                if service:
                    children_df = children_df[children_df["source"] == service]

                if not children_df.empty:
                    # Align columns
                    df = pd.concat([df, children_df], ignore_index=True)

        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime(r"%Y-%m-%d")
        return df

    def split_transaction(
        self, unique_id: int, source: str, splits: list[dict]
    ) -> bool:
        try:
            repo = self.get_repo_by_source(source)
            # 1. Mark parent
            repo.update_transaction_by_id(str(unique_id), {"type": "split_parent"})

            # 2. Add children
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
            # 1. Unmark parent
            repo.update_transaction_by_id(str(unique_id), {"type": "normal"})

            # 2. Delete children
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
            repo = self.get_repo_by_source(tx["source"])
            repo.update_transaction_by_id(
                str(tx["unique_id"]), {"category": category, "tag": tag}
            )

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
            # date is stored as string in this DB
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
        # Replicating original logic: get all tables, search.
        df = self.get_table()
        transaction = df[df["unique_id"] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found.")
        elif len(transaction) > 1:
            raise ValueError(f"Multiple transactions found with ID {transaction_id}.")
        return transaction.iloc[0]
