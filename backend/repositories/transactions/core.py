"""
Aggregating transactions repository.

Defines ``TransactionsRepository``, the main repository combining the five
per-table repositories (see ``service_repositories.py``) into one merged
view, with scraped-data ingestion (``ingestion.py``) and split handling
(``splits.py``) mixed in.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from backend.models.transaction import SplitTransaction
from backend.constants.providers import Services
from backend.constants.tables import Tables, TransactionsTableFields
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.transactions.ingestion import IngestionMixin
from backend.repositories.transactions.service_repositories import (
    BankRepository,
    CashRepository,
    CreditCardRepository,
    InsuranceRepository,
    ManualInvestmentTransactionsRepository,
    ManualTransactionDTO,
    ServiceRepository,
    T_service,
)
from backend.repositories.transactions.splits import SplitsMixin
from backend.utils.session_cache import session_cache_get, session_cache_set

logger = logging.getLogger(__name__)


class TransactionsRepository(IngestionMixin, SplitsMixin):
    """
    Main repository aggregating all transaction types.
    """

    tables = [
        Tables.CREDIT_CARD.value,
        Tables.BANK.value,
        Tables.CASH.value,
        Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        Tables.INSURANCE.value,
    ]

    unique_columns = ["id", "provider", "date", "amount"]

    UNCATEGORIZED_VALUES = ("", "Uncategorized")

    # Services excluded from aggregate cashflow calculations (CC double-counts
    # bank debits; insurance deposits are not regular expenses).
    _CASHFLOW_EXCLUDED = [Tables.CREDIT_CARD.value, Tables.INSURANCE.value]

    # Services excluded from itemized category breakdowns (insurance deposits
    # are not regular expenses, but CC items are kept for per-category detail).
    _ITEMIZED_EXCLUDED = [Tables.INSURANCE.value]

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
        self.insurance_repo = InsuranceRepository(db)
        self.split_repo = SplitTransactionsRepository(db)

        self.repo_map = {
            Tables.CREDIT_CARD.value: self.cc_repo,
            Tables.BANK.value: self.bank_repo,
            Tables.CASH.value: self.cash_repo,
            Tables.MANUAL_INVESTMENT_TRANSACTIONS.value: self.manual_investments_repo,
            Tables.INSURANCE.value: self.insurance_repo,
            Services.CREDIT_CARD.value: self.cc_repo,
            Services.BANK.value: self.bank_repo,
            Services.CASH.value: self.cash_repo,
            Services.MANUAL_INVESTMENTS.value: self.manual_investments_repo,
            Services.INSURANCE.value: self.insurance_repo,
        }

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

    def get_cashflow_transactions(self, **kwargs) -> pd.DataFrame:
        """Get transactions for aggregate totals (income, expenses, balances).

        Excludes credit card items (already captured as bank CC bill payments)
        and insurance deposits (not regular expenses).

        Parameters
        ----------
        **kwargs
            Forwarded to ``get_table`` (e.g. ``include_split_parents``).

        Returns
        -------
        pd.DataFrame
            Filtered transactions suitable for cashflow aggregations.
        """
        return self.get_table(exclude_services=self._CASHFLOW_EXCLUDED, **kwargs)

    def get_itemized_transactions(self, **kwargs) -> pd.DataFrame:
        """Get transactions for category breakdowns with itemized CC detail.

        Keeps credit card items for per-category analysis but excludes
        insurance deposits.

        Parameters
        ----------
        **kwargs
            Forwarded to ``get_table`` (e.g. ``include_split_parents``).

        Returns
        -------
        pd.DataFrame
            Filtered transactions suitable for category-level analysis.
        """
        return self.get_table(exclude_services=self._ITEMIZED_EXCLUDED, **kwargs)

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
        cache_key = (
            "transactions.get_table",
            service,
            include_split_parents,
            tuple(sorted(exclude_services or [])),
        )
        cached = session_cache_get(self.db, cache_key)
        if cached is not None:
            return cached

        df = self._get_base_transactions(service, exclude_services)

        if not include_split_parents:
            df = self._filter_split_parents(df)

        df = self._add_split_children(df, service, exclude_services)
        df = self._normalize_dates(df)

        session_cache_set(self.db, cache_key, df)
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
            Concatenated transactions. When no source has any rows, returns
            an empty DataFrame **with the canonical transaction columns**
            so downstream consumers can do ``df["date"]`` / ``df["unique_id"]``
            without a ``KeyError`` on a fresh / production-mode database.

        Raises
        ------
        ValueError
            If ``service`` does not match any registered source.
        """
        if service is not None:
            repo = self.get_repo_by_source(service)
            if repo is None:
                raise ValueError(f"Unknown service '{service}'")
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
            self.insurance_repo,
        ]
        dfs = [
            repo.get_table()
            for repo in all_repos
            if repo not in excluded_repos
        ]
        dfs = [df for df in dfs if not df.empty]

        if not dfs:
            return pd.DataFrame(
                columns=[f.value for f in TransactionsTableFields]
            )

        return pd.concat(dfs, ignore_index=True)

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

    def get_repo_by_source(self, source: str) -> ServiceRepository | None:
        """Look up the sub-repository for a given source/service name.

        Parameters
        ----------
        source : str
            Table name or service name (e.g. ``"credit_card_transactions"`` or
            ``"credit_card"``).

        Returns
        -------
        ServiceRepository or None
            The matching sub-repository instance, or ``None`` if ``source`` is
            not a recognized key in the repo_map. Callers that require a valid
            source must check for ``None`` (see ``get_table``); callers that
            tolerate unknown entries (e.g. ``exclude_services`` filtering) rely
            on the ``None`` return to skip them.
        """
        return self.repo_map.get(source)

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
            if repo is None:
                raise ValueError(f"Invalid source: '{tx['source']}'")
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

    def count_uncategorized(self) -> int:
        """Count uncategorized transactions across the merged (non-insurance) view.

        Counts rows whose category is NULL, empty, or ``"Uncategorized"`` in
        the four non-insurance transaction tables (excluding split parents,
        which the merged view replaces with their children), plus split-child
        rows from ``split_transactions`` whose parent source is one of those
        four tables. Split rows are counted per source table via a correlated
        ``EXISTS`` subquery against that table's parent row — mirroring
        ``_get_split_children``, which drops any split whose parent row no
        longer exists (orphaned splits). This means orphaned splits, and
        splits whose source is the insurance table or an unrecognized table,
        are excluded, exactly as the pandas merged view
        (``get_table(exclude_services=["insurances"])``) silently drops them.
        Pure SQL ``COUNT`` — no full-table DataFrame load.

        Returns
        -------
        int
            Number of uncategorized transactions in the merged view.
        """
        total = 0
        for repo in [
            self.cc_repo,
            self.bank_repo,
            self.cash_repo,
            self.manual_investments_repo,
        ]:
            model = repo.model
            stmt = (
                select(func.count())
                .select_from(model)
                .where(
                    or_(
                        model.category.is_(None),
                        model.category.in_(self.UNCATEGORIZED_VALUES),
                    ),
                    or_(model.type.is_(None), model.type != "split_parent"),
                )
            )
            total += int(self.db.execute(stmt).scalar_one())

            split_stmt = (
                select(func.count())
                .select_from(SplitTransaction)
                .where(
                    or_(
                        SplitTransaction.category.is_(None),
                        SplitTransaction.category.in_(self.UNCATEGORIZED_VALUES),
                    ),
                    SplitTransaction.source == repo.table,
                    exists(
                        select(1).where(
                            model.unique_id == SplitTransaction.transaction_id
                        )
                    ),
                )
            )
            total += int(self.db.execute(split_stmt).scalar_one())
        return total

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
        self.insurance_repo.nullify_category_and_tag(category, tag)

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
        self.insurance_repo.update_category_for_tag(old_category, new_category, tag)

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
        self.insurance_repo.nullify_category(category)

    def rename_category(self, old_name: str, new_name: str) -> None:
        """Rename category across all transaction tables."""
        self.cc_repo.rename_category(old_name, new_name)
        self.bank_repo.rename_category(old_name, new_name)
        self.cash_repo.rename_category(old_name, new_name)
        self.manual_investments_repo.rename_category(old_name, new_name)
        self.insurance_repo.rename_category(old_name, new_name)

    def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
        """Rename tag across all transaction tables."""
        self.cc_repo.rename_tag(category, old_tag, new_tag)
        self.bank_repo.rename_tag(category, old_tag, new_tag)
        self.cash_repo.rename_tag(category, old_tag, new_tag)
        self.manual_investments_repo.rename_tag(category, old_tag, new_tag)
        self.insurance_repo.rename_tag(category, old_tag, new_tag)

    def get_transaction_by_id(self, transaction_id: int, source: str) -> pd.Series:
        """Retrieve a single transaction row by its per-table unique_id.

        ``unique_id`` is a per-table auto-increment, so the source table is
        required — the same integer identifies unrelated transactions in
        different tables (see backend_repositories.md → "unique_id Is
        Per-Table").

        Parameters
        ----------
        transaction_id : int
            The unique_id to look up within ``source``.
        source : str
            Source table or service name (e.g. ``"bank_transactions"``).

        Returns
        -------
        pd.Series
            The matching transaction row, with a ``source`` entry naming the
            table it came from.

        Raises
        ------
        ValueError
            If ``source`` is not a known table/service name, or no
            transaction with that unique_id exists in it.
        """
        repo = self.repo_map.get(source)
        if repo is None:
            raise ValueError(f"Invalid source: {source}")
        record = self.db.get(repo.model, int(transaction_id))
        if record is None:
            raise ValueError(
                f"Transaction with ID {transaction_id} not found in {source}."
            )
        row = {
            k: v for k, v in record.__dict__.items() if k != "_sa_instance_state"
        }
        row["source"] = repo.model.__tablename__
        return pd.Series(row)
