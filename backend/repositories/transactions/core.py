"""
Aggregating transactions repository.

Defines ``TransactionsRepository``, the main repository combining the five
per-table repositories (see ``service_repositories.py``) into one merged
view, with scraped-data ingestion (``ingestion.py``) and split handling
(``splits.py``) mixed in.
"""

import logging
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.constants.tables import SERVICE_TO_TABLE, Tables, TransactionsTableFields
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.transaction import SplitTransaction, TransactionBase
from backend.repositories._sql import chunked, orm_to_dict
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
from backend.utils import data_cache
from backend.utils.session_cache import session_cache_get, session_cache_set

logger = logging.getLogger(__name__)


class TransactionsRepository(IngestionMixin, SplitsMixin):
    """Main repository aggregating all transaction types."""

    tables: ClassVar[list[str]] = [
        Tables.CREDIT_CARD.value,
        Tables.BANK.value,
        Tables.CASH.value,
        Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        Tables.INSURANCE.value,
    ]

    unique_columns: ClassVar[list[str]] = ["id", "provider", "date", "amount"]

    UNCATEGORIZED_VALUES = ("", "Uncategorized")

    # Services excluded from aggregate cashflow calculations (CC double-counts
    # bank debits; insurance deposits are not regular expenses).
    _CASHFLOW_EXCLUDED: ClassVar[list[str]] = [
        Tables.CREDIT_CARD.value,
        Tables.INSURANCE.value,
    ]

    # Services excluded from itemized category breakdowns (insurance deposits
    # are not regular expenses, but CC items are kept for per-category detail).
    _ITEMIZED_EXCLUDED: ClassVar[list[str]] = [Tables.INSURANCE.value]

    def __init__(self, db: Session) -> None:
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

        by_table = {repo.table: repo for repo in self._all_repos()}
        self.repo_map: dict[str, ServiceRepository] = {
            **by_table,
            **{service: by_table[table] for service, table in SERVICE_TO_TABLE.items()},
        }

    def _non_insurance_repos(self) -> list[ServiceRepository]:
        """Return the four sub-repositories behind the merged non-insurance view."""
        return [
            self.cc_repo,
            self.bank_repo,
            self.cash_repo,
            self.manual_investments_repo,
        ]

    def _all_repos(self) -> list[ServiceRepository]:
        """Return all five transaction sub-repositories."""
        return [*self._non_insurance_repos(), self.insurance_repo]

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
        ValidationException
            If ``service`` is not ``"cash"`` or ``"manual_investments"``.
        """
        if service == Services.CASH.value:
            return self.cash_repo.add_transaction(transaction)
        if service == Services.MANUAL_INVESTMENTS.value:
            return self.manual_investments_repo.add_transaction(transaction)
        raise ValidationException(
            f"service must be 'cash' or 'manual_investments'. Got '{service}'"
        )

    def get_cashflow_transactions(self, **kwargs: Any) -> pd.DataFrame:
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

    def get_itemized_transactions(self, **kwargs: Any) -> pd.DataFrame:
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

        def build() -> pd.DataFrame:
            df = self._get_base_transactions(service, exclude_services)

            if not include_split_parents:
                df = self._filter_split_parents(df)

            df = self._add_split_children(df, service, exclude_services)
            return self._normalize_dates(df)

        # Across requests too: ~20 dashboard endpoints each load this same
        # table before doing their own work, and every one of them paid the
        # full read + concat + date normalization. The copy is the caller's
        # (DataFrames here are routinely mutated in place).
        df = data_cache.cached(self.db, cache_key, build).copy()

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
        ValidationException
            If ``service`` does not match any registered source.
        """
        if service is not None:
            repo = self.get_repo_by_source(service)
            if repo is None:
                raise ValidationException(f"Unknown service '{service}'")
            return repo.get_table()

        excluded_repos = {
            repo
            for s in (exclude_services or [])
            if (repo := self.get_repo_by_source(s)) is not None
        }

        dfs = [
            repo.get_table() for repo in self._all_repos() if repo not in excluded_repos
        ]
        dfs = [df for df in dfs if not df.empty]

        if not dfs:
            return pd.DataFrame(columns=[f.value for f in TransactionsTableFields])

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
            A stored value that does not parse becomes ``NaN`` rather than
            failing the whole read — one corrupt row must not take every
            transactions/analytics endpoint down with it. Returns df
            unchanged if empty or if ``date`` column is absent.
        """
        if df.empty or "date" not in df.columns:
            return df
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime(
            r"%Y-%m-%d"
        )
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

    def get_record(self, source: str, unique_id: int) -> TransactionBase | None:
        """Return one transaction's ORM row from its source table.

        Parameters
        ----------
        source : str
            Table or service name the transaction lives in.
        unique_id : int
            The transaction's per-table ``unique_id``.

        Returns
        -------
        TransactionBase or None
            The row, or ``None`` when ``source`` is unknown or no row has
            that ``unique_id`` in it.
        """
        repo = self.get_repo_by_source(source)
        if repo is None:
            return None
        return self.db.execute(
            select(repo.model).where(repo.model.unique_id == unique_id)
        ).scalar_one_or_none()

    def get_records(self, source: str, unique_ids: list[int]) -> list[TransactionBase]:
        """Return the ORM rows of many transactions from one source table.

        Parameters
        ----------
        source : str
            Table or service name the transactions live in.
        unique_ids : list[int]
            Per-table ``unique_id`` values; queried in ``IN`` chunks.

        Returns
        -------
        list[TransactionBase]
            The rows that exist; empty when ``source`` is unknown.
        """
        repo = self.get_repo_by_source(source)
        if repo is None:
            return []
        rows: list[TransactionBase] = []
        for chunk in chunked(unique_ids):
            rows.extend(
                self.db.execute(
                    select(repo.model).where(repo.model.unique_id.in_(chunk))
                )
                .scalars()
                .all()
            )
        return rows

    def get_split_with_parent(
        self, split_id: int
    ) -> tuple[SplitTransaction, TransactionBase | None] | None:
        """Return a split slice together with the transaction it was cut from.

        Parameters
        ----------
        split_id : int
            Primary key of the ``split_transactions`` row.

        Returns
        -------
        tuple[SplitTransaction, TransactionBase or None] or None
            ``None`` when the slice does not exist; otherwise the slice and its
            parent row, the latter ``None`` when the slice's source is unknown
            or its parent is gone.
        """
        split = self.split_repo.get_split(split_id)
        if split is None:
            return None
        return split, self.get_record(split.source, split.transaction_id)

    def get_account_names(self, source: str, unique_ids: list[int]) -> list[str | None]:
        """Return the ``account_name`` of each existing transaction in a batch.

        Parameters
        ----------
        source : str
            Table or service name the transactions live in.
        unique_ids : list[int]
            Per-table ``unique_id`` values; queried in ``IN`` chunks.

        Returns
        -------
        list[str or None]
            One entry per matched row (unordered, may repeat).

        Raises
        ------
        ValidationException
            If ``source`` is not a known table/service name.
        """
        repo = self._require_repo(source)
        names: list[str | None] = []
        for chunk in chunked(unique_ids):
            names.extend(
                self.db.execute(
                    select(repo.model.account_name).where(
                        repo.model.unique_id.in_(chunk)
                    )
                )
                .scalars()
                .all()
            )
        return names

    def bulk_update_fields(
        self, source: str, unique_ids: list[int], values: dict[str, Any]
    ) -> None:
        """Write the same field values to many transactions in one commit.

        Parameters
        ----------
        source : str
            Table or service name the transactions live in.
        unique_ids : list[int]
            Per-table ``unique_id`` values; ids that do not exist are simply
            not matched. Updated in ``IN`` chunks.
        values : dict[str, Any]
            Column name to new value.

        Raises
        ------
        ValidationException
            If ``source`` is not a known table/service name.
        """
        repo = self._require_repo(source)
        for chunk in chunked(unique_ids):
            self.db.execute(
                update(repo.model)
                .where(repo.model.unique_id.in_(chunk))
                .values(**values)
            )
        self.db.commit()

    def _require_repo(self, source: str) -> ServiceRepository:
        """Return the sub-repository for ``source`` or raise ``ValidationException``."""
        repo = self.get_repo_by_source(source)
        if repo is None:
            raise ValidationException(f"Invalid source: '{source}'")
        return repo

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
        if result is None:
            return None
        try:
            return datetime.strptime(result, "%Y-%m-%d")
        except ValueError:
            return None

    def get_all_table_names(self) -> list[str]:
        """Return the list of all transaction table names.

        Returns
        -------
        list[str]
            Copy of the class-level ``tables`` list containing the five
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
        for repo in self._non_insurance_repos():
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

    def get_category_last_used(self) -> dict[str, str]:
        """Return each category's most recent transaction date.

        Scans the four non-insurance transaction tables plus their split
        children, mirroring the merged view used elsewhere: ``split_parent``
        rows are skipped (their children replace them) and split children take
        their date from the parent row, which they are joined to on both
        ``unique_id`` and ``source`` because ``unique_id`` is a per-table
        auto-increment. Orphaned splits are dropped by the inner join, exactly
        as the pandas merged view drops them. Insurance transactions are
        excluded. Pure SQL ``MAX``/``GROUP BY`` — no DataFrame load.

        Dates are ``YYYY-MM-DD`` strings, so lexicographic ``MAX`` is
        chronologically correct.

        Returns
        -------
        dict[str, str]
            Mapping of category name to its latest transaction date. Categories
            with no transactions at all are absent from the mapping.
        """
        last_used: dict[str, str] = {}

        def _record(category: str | None, date_value: str | None) -> None:
            if not category or not date_value:
                return
            current = last_used.get(category)
            if current is None or date_value > current:
                last_used[category] = date_value

        for repo in self._non_insurance_repos():
            model = repo.model

            direct_stmt = (
                select(model.category, func.max(model.date))
                .where(
                    model.category.is_not(None),
                    or_(model.type.is_(None), model.type != "split_parent"),
                )
                .group_by(model.category)
            )
            for category, date_value in self.db.execute(direct_stmt).all():
                _record(category, date_value)

            split_stmt = (
                select(SplitTransaction.category, func.max(model.date))
                .join(model, model.unique_id == SplitTransaction.transaction_id)
                .where(
                    SplitTransaction.category.is_not(None),
                    SplitTransaction.source == repo.table,
                )
                .group_by(SplitTransaction.category)
            )
            for category, date_value in self.db.execute(split_stmt).all():
                _record(category, date_value)

        return last_used

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
        Delegates to all five sub-repositories (credit card, bank, cash,
        manual investments, insurance).
        """
        for repo in self._all_repos():
            repo.nullify_category_and_tag(category, tag)

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
        Delegates to all five sub-repositories.
        """
        for repo in self._all_repos():
            repo.update_category_for_tag(old_category, new_category, tag)

    def nullify_category(self, category: str) -> None:
        """Set category and tag to NULL for all transactions in a category.

        Parameters
        ----------
        category : str
            Category name to clear across all transaction tables.

        Notes
        -----
        Delegates to all five sub-repositories.
        """
        for repo in self._all_repos():
            repo.nullify_category(category)

    def rename_category(self, old_name: str, new_name: str) -> None:
        """Rename category across all transaction tables."""
        for repo in self._all_repos():
            repo.rename_category(old_name, new_name)

    def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
        """Rename tag across all transaction tables."""
        for repo in self._all_repos():
            repo.rename_tag(category, old_tag, new_tag)

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
        EntityNotFoundException
            If ``source`` is not a known table/service name, or no
            transaction with that unique_id exists in it.
        """
        repo = self.repo_map.get(source)
        if repo is None:
            raise EntityNotFoundException(f"Invalid source: {source}")
        record = self.db.get(repo.model, int(transaction_id))
        if record is None:
            raise EntityNotFoundException(
                f"Transaction with ID {transaction_id} not found in {source}."
            )
        row = orm_to_dict(record)
        row["source"] = repo.model.__tablename__
        return pd.Series(row)
