"""
Transactions service.

This module provides business logic for transaction operations: the merged
analysis frame (splits expanded, prior-wealth rows appended), manual
transaction CRUD, splitting, bulk tagging, and the side effects every write
must trigger.
"""

from datetime import date, datetime
from typing import Any, ClassVar, Literal

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    PROTECTED_TAGS,
    IncomeCategories,
)
from backend.constants.providers import Services
from backend.constants.tables import (
    TRANSACTION_SOURCES,
    Tables,
    TransactionsTableFields,
    table_aliases,
)
from backend.errors import (
    BadRequestException,
    EntityNotFoundException,
    ForbiddenException,
    ValidationException,
)
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions import (
    ManualTransactionDTO,
    TransactionsRepository,
    TxRef,
    transaction_table,
)
from backend.services.transaction_write_effects import TransactionWriteEffects
from backend.utils.session_cache import session_cache_get, session_cache_set

# `split_id` holds the primary key of a `split_transactions` row, or nothing at
# all for a transaction that was never split. Assigning bare `None` yields an
# `object` column, while the split-expansion path yields `float64` (NaN for the
# unsplit rows) — so frames built by different paths disagreed on the dtype of a
# column that is frequently all-NA. `pd.concat` reconciles that today by
# ignoring the all-NA side, but warns that it will stop doing so. Pinning every
# synthesised column to the same dtype keeps the frames uniform.
SPLIT_ID_DTYPE = "float64"

# Splits are money slices of one transaction, so they must add up to it. Money
# is stored as a float, so allow a cent of accumulated rounding drift.
SPLIT_SUM_TOLERANCE = 0.01


def _empty_split_id(index: pd.Index) -> pd.Series:
    """Build an all-missing ``split_id`` column with the canonical dtype."""
    return pd.Series(index=index, dtype=SPLIT_ID_DTYPE)


class TransactionsService:
    """
    Service for transaction business logic.

    Wraps ``TransactionsRepository`` (and its split repository) with split
    handling, prior-wealth rows, and the cash-balance / investment
    recalculations that follow every write.
    """

    ANALYSIS_COLUMNS: ClassVar[list[str]] = [
        TransactionsTableFields.ID.value,
        TransactionsTableFields.DATE.value,
        TransactionsTableFields.PROVIDER.value,
        TransactionsTableFields.ACCOUNT_NAME.value,
        TransactionsTableFields.ACCOUNT_NUMBER.value,
        TransactionsTableFields.DESCRIPTION.value,
        TransactionsTableFields.AMOUNT.value,
        TransactionsTableFields.CATEGORY.value,
        TransactionsTableFields.TAG.value,
        TransactionsTableFields.STATUS.value,
        TransactionsTableFields.TYPE.value,
        TransactionsTableFields.UNIQUE_ID.value,
        TransactionsTableFields.SOURCE.value,
        TransactionsTableFields.SPLIT_ID.value,
    ]

    def __init__(self, db: Session) -> None:
        """
        Initialize the transactions service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.transactions_repository = TransactionsRepository(db)
        self.balance_repo = BankBalanceRepository(db)
        self.investments_repo = InvestmentsRepository(db)
        self.write_effects = TransactionWriteEffects(db)

    def get_data_for_analysis(
        self, include_split_parents: bool = False
    ) -> pd.DataFrame:
        """
        Get the merged transactions table for analysis, including prior-wealth rows.

        Combines credit cards, banks, cash, and manual investment tables.
        Appends synthetic prior-wealth rows from bank balances and investment
        ``prior_wealth_amount`` fields.

        Parameters
        ----------
        include_split_parents : bool, optional
            When ``True``, includes parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        pd.DataFrame
            Merged DataFrame with all transaction sources and prior-wealth rows.
            Returns an empty DataFrame if no data exists.
        """
        cache_key = ("transactions.data_for_analysis", include_split_parents)
        cached = session_cache_get(self.db, cache_key)
        if cached is not None:
            return cached

        cc_data = self.get_table_for_analysis(
            Services.CREDIT_CARD.value, include_split_parents
        )
        bank_data = self.get_table_for_analysis(
            Services.BANK.value, include_split_parents
        )
        cash_data = self.get_table_for_analysis(
            Services.CASH.value, include_split_parents
        )
        manual_investments_data = self.get_table_for_analysis(
            Services.MANUAL_INVESTMENTS.value, include_split_parents
        )
        dfs = [cc_data, bank_data, cash_data, manual_investments_data]

        prior_wealth_df = self._build_bank_prior_wealth_rows()
        if not prior_wealth_df.empty:
            dfs.append(prior_wealth_df)

        investment_prior_wealth_df = self._build_investment_prior_wealth_rows()
        if not investment_prior_wealth_df.empty:
            dfs.append(investment_prior_wealth_df)

        dfs = [df for df in dfs if not df.empty]
        if not dfs:
            empty = pd.DataFrame(columns=self.ANALYSIS_COLUMNS)
            session_cache_set(self.db, cache_key, empty)
            return empty
        merged = pd.concat(dfs, ignore_index=True)
        session_cache_set(self.db, cache_key, merged)
        return merged

    def _build_bank_prior_wealth_rows(self) -> pd.DataFrame:
        """Build synthetic prior wealth rows from bank balance records."""
        balances_df = self.balance_repo.get_all()
        if balances_df.empty:
            return pd.DataFrame()

        rows = [
            self._prior_wealth_row(
                row_id=f"bank_pw_{bal['id']}",
                date_value=bal.get("last_manual_update") or bal.get("created_at", ""),
                provider=bal["provider"],
                account_name=bal["account_name"],
                description=f"Prior Wealth ({bal['provider']} - {bal['account_name']})",
                amount=bal["prior_wealth_amount"],
                source="bank_balances",
            )
            for _, bal in balances_df.iterrows()
            if bal["prior_wealth_amount"] != 0
        ]
        return self._prior_wealth_frame(rows)

    def _build_investment_prior_wealth_rows(self) -> pd.DataFrame:
        """Build synthetic prior wealth rows from Investment.prior_wealth_amount.

        Mirrors _build_bank_prior_wealth_rows for bank accounts.
        Only includes open (non-closed) investments with prior_wealth_amount != 0.
        """
        investments_df = self.investments_repo.get_all_investments(include_closed=False)
        if investments_df.empty:
            return pd.DataFrame()

        rows = [
            self._prior_wealth_row(
                row_id=f"inv_pw_{inv['id']}",
                date_value=inv.get("created_date", ""),
                provider=Services.MANUAL_INVESTMENTS.value,
                account_name=inv["name"],
                description=f"Prior Wealth ({inv['name']})",
                amount=inv["prior_wealth_amount"],
                source="investments",
            )
            for _, inv in investments_df.iterrows()
            if inv["prior_wealth_amount"] != 0
        ]
        return self._prior_wealth_frame(rows)

    @staticmethod
    def _prior_wealth_row(
        *,
        row_id: str,
        date_value: Any,
        provider: str,
        account_name: str,
        description: str,
        amount: float,
        source: str,
    ) -> dict[str, Any]:
        """Build one synthetic ``Other Income / Prior Wealth`` analysis row."""
        return {
            TransactionsTableFields.ID.value: row_id,
            TransactionsTableFields.DATE.value: date_value,
            TransactionsTableFields.PROVIDER.value: provider,
            TransactionsTableFields.ACCOUNT_NAME.value: account_name,
            TransactionsTableFields.ACCOUNT_NUMBER.value: None,
            TransactionsTableFields.DESCRIPTION.value: description,
            TransactionsTableFields.AMOUNT.value: amount,
            TransactionsTableFields.CATEGORY.value: IncomeCategories.OTHER_INCOME.value,
            TransactionsTableFields.TAG.value: PRIOR_WEALTH_TAG,
            TransactionsTableFields.UNIQUE_ID.value: row_id,
            TransactionsTableFields.SOURCE.value: source,
            TransactionsTableFields.SPLIT_ID.value: None,
            TransactionsTableFields.TYPE.value: "normal",
        }

    @staticmethod
    def _prior_wealth_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Frame prior-wealth rows with the canonical ``split_id`` dtype."""
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).astype(
            {TransactionsTableFields.SPLIT_ID.value: SPLIT_ID_DTYPE}
        )

    def update_tagging_by_id(
        self,
        table_name: str,
        unique_id: int | str,
        category: str | None,
        tag: str | None,
    ) -> int:
        """
        Update the category and tag for a transaction identified by table and ID.

        Refund money linked to the transaction follows it to the new tag.

        Parameters
        ----------
        table_name : str
            Source table name (e.g. ``"credit_card_transactions"``) or its
            service alias (``"credit_cards"``) — every spelling the
            repository dispatches on.
        unique_id : int or str
            Unique ID of the transaction to update.
        category : str or None
            New category value. Empty strings are normalised to ``None``.
        tag : str or None
            New tag value. Empty strings are normalised to ``None``.

        Returns
        -------
        int
            How many linked refunds were moved to the new tag.

        Raises
        ------
        ValidationException
            If ``table_name`` does not match any known transaction table, or
            ``unique_id`` is not an integer.
        """
        ref = TxRef.parse(table_name, unique_id)
        category = self._normalize_empty_string(category)
        tag = self._normalize_empty_string(tag)
        with self.write_effects.track(ref.table, [ref.unique_id]):
            self.transactions_repository.update_tagging(ref, category, tag)
        return self._cascade_to_linked_refunds(ref.table, [ref.unique_id])

    def _cascade_to_linked_refunds(self, source: str, unique_ids: list[int]) -> int:
        """Move refund money linked to retagged purchases to their new tag.

        Parameters
        ----------
        source : str
            Table or service name of the retagged transactions.
        unique_ids : list[int]
            The retagged transactions.

        Returns
        -------
        int
            How many links had their refund money moved.
        """
        from backend.services.refund_tag_alignment import RefundTagAlignmentService

        return RefundTagAlignmentService(self.db).cascade_from_transactions(
            source, unique_ids
        )

    def get_transactions_by_tag(
        self, category: str, tag: str | None = None
    ) -> pd.DataFrame:
        """
        Get all transactions filtered by category and optionally tag.

        Parameters
        ----------
        category : str
            Category to filter by.
        tag : str, optional
            Tag to further filter by. If ``None``, all tags in the category
            are returned.

        Returns
        -------
        pd.DataFrame
            Matching transactions, reset index. Empty if no data.
        """
        df = self.get_data_for_analysis()
        if df.empty:
            return df
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        investment_df = df[df[category_col] == category]
        if tag:
            investment_df = investment_df[investment_df[tag_col] == tag]
        return investment_df.reset_index(drop=True)

    def get_merged_transactions(
        self,
        service: str | None = None,
        include_split_parents: bool = False,
        exclude_services: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Get the merged multi-table transactions frame.

        Thin passthrough to :meth:`TransactionsRepository.get_table` so routes
        never instantiate repositories directly.

        Parameters
        ----------
        service : str, optional
            Restrict to a single service/table.
        include_split_parents : bool, optional
            Keep split-parent rows (marked ``type="split_parent"``).
        exclude_services : list[str], optional
            Services/tables to exclude from the merge.

        Returns
        -------
        pd.DataFrame
            Merged transactions with splits expanded.

        Raises
        ------
        ValidationException
            If ``service`` is not a recognized service/table name.
        """
        return self.transactions_repository.get_table(
            service=service,
            include_split_parents=include_split_parents,
            exclude_services=exclude_services,
        )

    def get_transaction(self, transaction_id: int, source: str) -> pd.Series:
        """
        Get a single transaction by per-table id and source table.

        Parameters
        ----------
        transaction_id : int
            The unique_id within ``source``.
        source : str
            Source table or service name.

        Returns
        -------
        pd.Series
            The matching transaction row.

        Raises
        ------
        ValidationException
            If the source is unknown or the id is not an integer.
        EntityNotFoundException
            If no transaction matches.
        """
        return self.transactions_repository.get_transaction_by_id(
            TxRef.parse(source, transaction_id)
        )

    @staticmethod
    def _normalize_empty_string(value: str | None) -> str | None:
        """Convert empty strings to None for category/tag fields."""
        return None if value == "" else value

    @staticmethod
    def _validate_date(value: str | date | datetime) -> str:
        """Normalise a user-supplied date to the stored ``YYYY-MM-DD`` form.

        Dates are stored as strings and compared lexicographically, so an
        unparseable value written once would sort wrongly forever and break
        every ``to_datetime`` downstream.

        Parameters
        ----------
        value : str or date or datetime
            The requested date.

        Returns
        -------
        str
            ``YYYY-MM-DD``.

        Raises
        ------
        ValidationException
            If ``value`` is not a ``YYYY-MM-DD`` string or date object.
        """
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValidationException(
                f"Invalid date '{value}': expected YYYY-MM-DD"
            ) from None

    def create_transaction(self, data: dict[str, Any], service: str) -> None:
        """
        Create a new manual transaction with validation and normalization.

        Parameters
        ----------
        data : dict
            Transaction data including date, description, amount, account_name,
            and optional provider, account_number, category, tag.
        service : str
            The service type: 'cash' or 'manual_investments'.

        Raises
        ------
        ValidationException
            If service is not 'cash' or 'manual_investments'.
        RuntimeError
            If the transaction could not be created.
        """
        if service not in [Services.CASH.value, Services.MANUAL_INVESTMENTS.value]:
            raise ValidationException(
                "Can only create cash or manual_investments transactions"
            )

        provider = "CASH" if service == Services.CASH.value else data.get("provider")

        tx = ManualTransactionDTO(
            date=datetime.combine(data["date"], datetime.min.time()),
            account_name=data["account_name"],
            description=data["description"],
            amount=data["amount"],
            provider=provider,
            account_number=data.get("account_number"),
            category=self._normalize_empty_string(data.get("category")),
            tag=self._normalize_empty_string(data.get("tag")),
        )
        with self.write_effects.track(service) as touched:
            touched.include(tx.account_name, tx.category, tx.tag)
            if not self.transactions_repository.add_transaction(tx, service):
                raise RuntimeError("Failed to create transaction")

    def _filter_updates_for_source(
        self, source: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply per-source permission rules and normalization to an update dict.

        Manual sources (cash, manual investments) may edit date/account_name/
        description/amount (and provider — forced to "CASH" for cash rows);
        scraped sources may only edit category/tag. Empty category/tag strings
        are normalised to ``None``.

        Parameters
        ----------
        source : str
            Canonical source table name.
        updates : dict
            Raw requested updates.

        Returns
        -------
        dict
            The subset of ``updates`` this source is allowed to write.

        Raises
        ------
        ValidationException
            If a manual source's ``date`` is not ``YYYY-MM-DD``.
        """
        is_manual = source in [
            Tables.CASH.value,
            Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        ]
        filtered_updates: dict[str, Any] = {}
        if is_manual:
            if updates.get("date") is not None:
                filtered_updates["date"] = self._validate_date(updates["date"])
            if updates.get("account_name") is not None:
                filtered_updates["account_name"] = updates["account_name"]
            if updates.get("description") is not None:
                filtered_updates["description"] = updates["description"]
            if updates.get("amount") is not None:
                filtered_updates["amount"] = updates["amount"]
            if source == Tables.CASH.value:
                filtered_updates["provider"] = "CASH"
            elif updates.get("provider") is not None:
                filtered_updates["provider"] = updates["provider"]

        if updates.get("category") is not None:
            filtered_updates["category"] = self._normalize_empty_string(
                updates["category"]
            )
        if updates.get("tag") is not None:
            filtered_updates["tag"] = self._normalize_empty_string(updates["tag"])
        return filtered_updates

    def update_transaction(
        self, unique_id: int | str, source: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update a transaction with source-based permission constraints.

        Manual sources (``cash``, ``manual_investment_transactions``) may edit
        ``description``, ``amount``, ``provider``, ``date``, and
        ``account_name`` in addition to ``category`` and ``tag``. Scraped
        sources can only update ``category`` and ``tag``. When
        ``account_name`` changes on a cash transaction, balances are
        recalculated for both the old and new account. Empty strings in
        category/tag are normalised to ``None``. A new category or tag carries
        the refund money linked to the transaction along with it.

        Parameters
        ----------
        unique_id : int or str
            Unique ID of the transaction to update.
        source : str
            Source table name (e.g. ``"cash"``, ``"credit_card_transactions"``).
        updates : dict
            Fields to update. Recognised keys: ``description``, ``amount``,
            ``provider``, ``date``, ``account_name``, ``category``, ``tag``.

        Returns
        -------
        dict
            ``updated`` — whether updates were applied (``False`` when no
            applicable fields were provided) — and ``refunds_retagged``, how
            many linked refunds followed a new category or tag.

        Raises
        ------
        ValidationException
            If ``source`` is unknown, ``unique_id`` is not an integer, or a
            manual date is malformed.
        EntityNotFoundException
            If no transaction with ``unique_id`` exists in ``source``.
        """
        ref = TxRef.parse(source, unique_id)

        # A missing row is a 404, not a silent "no_changes".
        if self.transactions_repository.get_record(ref) is None:
            raise EntityNotFoundException(
                f"Transaction {ref.unique_id} not found in {ref.table}"
            )

        filtered_updates = self._filter_updates_for_source(ref.table, updates)

        if not filtered_updates:
            return {"updated": False, "refunds_retagged": 0}

        with self.write_effects.track(ref.table, [ref.unique_id]):
            result = self.transactions_repository.repo_for(
                ref.table
            ).update_transaction_by_unique_id(ref.unique_id, filtered_updates)

        retagged = 0
        if result and ({"category", "tag"} & filtered_updates.keys()):
            retagged = self._cascade_to_linked_refunds(ref.table, [ref.unique_id])
        return {"updated": bool(result), "refunds_retagged": retagged}

    def delete_transaction(self, unique_id: int | str, source: str) -> None:
        """
        Delete a transaction with source validation and protection checks.

        Only ``cash_transactions`` and ``manual_investment_transactions`` sources
        are deletable. System-generated Prior Wealth transactions (identified by
        matching tag and account name) are protected and cannot be deleted.
        After deletion, the cash prior-wealth offset or investment prior-wealth
        is recalculated as needed.

        Parameters
        ----------
        unique_id : int or str
            Unique ID of the transaction to delete.
        source : str
            Source table name; must be ``"cash_transactions"`` or
            ``"manual_investment_transactions"``.

        Raises
        ------
        ValidationException
            If ``source`` is not a known table or service name, or
            ``unique_id`` is not an integer. A malformed request, not a
            permission problem — without this check it read as "you may not
            delete this" rather than "that table does not exist".
        ForbiddenException
            If the source does not allow deletion or the transaction is a
            protected system-generated record.
        EntityNotFoundException
            If the transaction is not found or deletion fails.
        """
        ref = TxRef.parse(source, unique_id)
        if ref.table not in [
            Tables.CASH.value,
            Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        ]:
            raise ForbiddenException(
                f"Deletion of {ref.table} transactions is prohibited"
            )

        tx_record = self.transactions_repository.get_record(ref)

        if not tx_record:
            raise EntityNotFoundException("Transaction not found")

        tag = getattr(tx_record, "tag", None)
        account_name = getattr(tx_record, "account_name", None)
        if tag in PROTECTED_TAGS and account_name in PROTECTED_TAGS:
            raise ForbiddenException(
                f"Cannot manually delete system-generated {tag} transaction"
            )

        with self.write_effects.track(ref.table, [ref.unique_id]):
            if not self.transactions_repository.repo_for(
                ref.table
            ).delete_transaction_by_unique_id(ref.unique_id):
                raise EntityNotFoundException(
                    "Transaction not found or deletion failed"
                )

        self._purge_dependent_records([ref.unique_id], ref.table)

    def _purge_dependent_records(self, unique_ids: list[int], source: str) -> None:
        """
        Remove every record that pointed at now-deleted transactions.

        Splits, pending refunds (and their links), refund-source notes and
        budget month overrides all reference a transaction by
        ``(source_table, unique_id)``. ``unique_id`` is a per-table
        auto-increment and SQLite reuses rowids, so an orphan left behind is
        not merely dead data — the next transaction created in that table
        silently inherits it, landing in the wrong budget month or carrying
        someone else's refund.

        Takes a list rather than a single id so wiping a whole account costs a
        handful of bulk DELETEs instead of one round-trip per transaction (a
        2000-row account took over 5 s row-by-row).

        Parameters
        ----------
        unique_ids : list[int]
            unique_ids of the deleted transactions. Empty is a no-op.
        source : str
            Table name the transactions were deleted from.
        """
        if not unique_ids:
            return

        from backend.repositories.budget_month_override_repository import (
            BudgetMonthOverrideRepository,
        )
        from backend.repositories.pending_refunds_repository import (
            PendingRefundsRepository,
        )

        # Older rows may store the service name ("cash") rather than the table
        # name ("cash_transactions"); accept every spelling that resolves here.
        source_aliases = sorted(set(table_aliases(source)))

        # Slices are about to go too; their ids must be known before the
        # DELETE so the records pointing at them can follow.
        split_ids = self.transactions_repository.get_split_ids_for_transactions(
            unique_ids, source
        )
        self.transactions_repository.split_repo.delete_splits_for_transactions(
            unique_ids, source
        )

        PendingRefundsRepository(self.db).delete_for_transactions(
            source_aliases, unique_ids
        )

        BudgetMonthOverrideRepository(self.db).delete_for_sources(
            "transaction", unique_ids, source_aliases
        )

        self._purge_split_dependents(split_ids)

    def _purge_split_dependents(self, split_ids: list[int]) -> None:
        """
        Remove every record that pointed at now-deleted split slices.

        A pending refund or budget month override can be scoped to a slice
        (``source_type="split"``), and a refund link can cover one; the link
        outlives the slice and goes back to covering the whole transaction.
        ``split_transactions`` ids are recycled by SQLite just like
        transaction ids, so an orphan would be inherited by
        the next slice created — including the replacement slices of a
        re-split.

        Parameters
        ----------
        split_ids : list[int]
            Primary keys of the deleted ``split_transactions`` rows. Empty is
            a no-op.
        """
        if not split_ids:
            return

        from backend.repositories.budget_month_override_repository import (
            BudgetMonthOverrideRepository,
        )
        from backend.repositories.pending_refunds_repository import (
            PendingRefundsRepository,
        )

        pending_repo = PendingRefundsRepository(self.db)
        pending_repo.delete_for_splits(split_ids)
        pending_repo.unpin_links_from_splits(split_ids)

        # Split ids are global, but the override table is keyed by source
        # table as well; accept every spelling a client may have stored.
        spellings = sorted(TRANSACTION_SOURCES)
        spellings.append(Tables.SPLIT_TRANSACTIONS.value)
        BudgetMonthOverrideRepository(self.db).delete_for_sources(
            "split", split_ids, spellings
        )

    def delete_account_data(
        self, service: str, provider: str, account_name: str
    ) -> dict[str, Any]:
        """Delete every transaction for one account, plus its dependent records.

        Used when the user removes a connected account and chooses to discard
        its history. Splits, pending refunds, refund links, source notes and
        budget month overrides are purged alongside the transactions — leaving
        them behind would orphan them onto whichever transaction next reuses
        the rowid.

        Parameters
        ----------
        service : str
            Service or table name identifying which transaction table holds
            the account (e.g. ``"banks"`` or ``"bank_transactions"``).
        provider : str
            Provider identifier (e.g. ``"hapoalim"``).
        account_name : str
            Account name as stored on the transactions.

        Returns
        -------
        dict[str, Any]
            ``{"transactions_deleted": int}``.

        Raises
        ------
        ValidationException
            If ``service`` does not map to a known transaction table.
        """
        repo = self.transactions_repository.repo_for(service)
        source = repo.table
        unique_ids = repo.get_unique_ids_for_account(provider, account_name)

        # Purge dependents first: once the transactions are gone their ids can
        # be handed to new rows, and an orphan would attach to those instead.
        self._purge_dependent_records(unique_ids, source)

        deleted = repo.delete_transactions_for_account(provider, account_name)
        return {"transactions_deleted": deleted}

    def split_transaction(
        self, unique_id: int | str, source: str, splits: list[dict[str, Any]]
    ) -> None:
        """Split a transaction into multiple partial amounts across categories.

        The slices must add up to the parent amount (within
        ``SPLIT_SUM_TOLERANCE``) — the same invariant the split modal
        enforces client-side. Without the server-side check a crafted
        payload silently inflated every total that reads the merged view.
        Slices of mixed sign are accepted as long as they balance.

        Parameters
        ----------
        unique_id : int or str
            Unique ID of the transaction to split.
        source : str
            Source table or service name (e.g. ``"bank_transactions"``).
        splits : list[dict]
            One entry per resulting split, each with ``amount``, ``category``,
            ``tag``.

        Raises
        ------
        ValidationException
            If the source is not recognized, ``unique_id`` is not an integer,
            ``splits`` is empty or its amounts don't sum to the parent.
        BadRequestException
            If the split fails to commit.
        EntityNotFoundException
            If no transaction with ``unique_id`` exists in ``source``.
        """
        ref = TxRef.parse(source, unique_id)
        if not splits:
            # A zero-slice split flipped the parent to ``split_parent`` with
            # no children, hiding the transaction from the merged view.
            raise ValidationException("A split needs at least one slice")

        parent = self.transactions_repository.get_transaction_by_id(ref)
        parent_amount = float(parent["amount"])
        total = sum(float(split["amount"]) for split in splits)
        if abs(total - parent_amount) > SPLIT_SUM_TOLERANCE:
            raise ValidationException(
                f"Split amounts must sum to the transaction amount "
                f"({parent_amount:.2f}); got {total:.2f}"
            )

        # A re-split replaces the slices; whatever pointed at the old ones
        # must not survive onto the new (possibly id-recycled) slices.
        old_split_ids = self.transactions_repository.get_split_ids_for_transactions(
            [ref.unique_id], ref.table
        )
        success = self.transactions_repository.split_transaction(ref, splits)
        if not success:
            raise BadRequestException("Failed to split transaction")
        self._purge_split_dependents(old_split_ids)

    def revert_split(self, unique_id: int | str, source: str) -> None:
        """Revert a split transaction back to a normal transaction.

        Parameters
        ----------
        unique_id : int or str
            Unique ID of the split-parent transaction to revert.
        source : str
            Source table or service name (e.g. ``"bank_transactions"``).

        Raises
        ------
        ValidationException
            If the source is not recognized or ``unique_id`` is not an integer.
        BadRequestException
            If the revert fails to commit.
        EntityNotFoundException
            If no transaction with ``unique_id`` exists in ``source``, or the
            transaction is not a split parent.
        """
        ref = TxRef.parse(source, unique_id)
        parent = self.transactions_repository.get_transaction_by_id(ref)
        if parent.get("type") != "split_parent":
            raise EntityNotFoundException(
                f"Transaction {ref.unique_id} in {ref.table} is not split"
            )

        split_ids = self.transactions_repository.get_split_ids_for_transactions(
            [ref.unique_id], ref.table
        )
        success = self.transactions_repository.revert_split(ref)
        if not success:
            raise BadRequestException("Failed to revert split")
        self._purge_split_dependents(split_ids)

    def bulk_tag_transactions(
        self,
        transaction_ids: list[int],
        source: str,
        category: str | None,
        tag: str | None,
        description: str | None = None,
        account_name: str | None = None,
        date: str | None = None,
        amount: float | None = None,
    ) -> int:
        """
        Apply the same category, tag, and optional fields to multiple transactions.

        For manual sources (``cash``, ``manual_investment_transactions``),
        ``description``, ``account_name``, ``date``, and ``amount`` are also
        applied when provided; every other source keeps them. This is one
        ``UPDATE ... WHERE unique_id IN (...)`` and one commit for the whole
        batch — ids that do not exist are simply not matched — followed by a
        single cash-balance recalculation per affected account.

        Parameters
        ----------
        transaction_ids : list[int]
            List of unique IDs to update.
        source : str
            Source table name shared by all transactions.
        category : str or None
            Category to apply. Empty strings are normalised to ``None``.
        tag : str or None
            Tag to apply. Empty strings are normalised to ``None``.
        description : str or None, optional
            Description to apply. Only written for manual sources.
        account_name : str or None, optional
            Account name to apply. Only written for manual sources.
        date : str or None, optional
            Date string to apply. Only written for manual sources.
        amount : float or None, optional
            Amount to apply. Only written for manual sources.

        Returns
        -------
        int
            How many linked refunds followed the transactions to their new
            category and tag.

        Raises
        ------
        ValidationException
            If ``source`` is not a known table/service name, or a manual
            ``date`` is not ``YYYY-MM-DD``.
        """
        updates: dict[str, Any] = {
            "category": category,
            "tag": tag,
        }
        if description is not None:
            updates["description"] = description
        if account_name is not None:
            updates["account_name"] = account_name
        if date is not None:
            updates["date"] = date
        if amount is not None:
            updates["amount"] = amount

        table = transaction_table(source)

        filtered_updates = self._filter_updates_for_source(table, updates)
        if not filtered_updates or not transaction_ids:
            return 0

        ids = [TxRef.parse(table, uid).unique_id for uid in transaction_ids]

        # One commit for the whole batch instead of a commit per row.
        with self.write_effects.track(table, ids):
            self.transactions_repository.bulk_update_fields(
                table, ids, filtered_updates
            )
        return self._cascade_to_linked_refunds(table, ids)

    def get_latest_data_date(self) -> datetime | None:
        """
        Get the minimum of the latest transaction dates across all tables.

        Returns the minimum so that the displayed "latest date" reflects the
        most outdated source (i.e. all sources have data up to at least this
        date). Tables with no rows are not "outdated" — they are unused — so
        they are ignored rather than dragging the result down to a
        placeholder date.

        Returns
        -------
        datetime or None
            The minimum latest-date across the populated tables, or ``None``
            when no table has any data.
        """
        latest_dates = [
            latest
            for table in self.transactions_repository.get_all_table_names()
            if (
                latest := self.transactions_repository.get_latest_date_from_table(table)
            )
            is not None
        ]
        return min(latest_dates) if latest_dates else None

    def count_uncategorized(self) -> int:
        """Count uncategorized transactions in the merged non-insurance view.

        Returns
        -------
        int
            Number of transactions with no category, an empty category, or
            the literal ``"Uncategorized"`` category.
        """
        return self.transactions_repository.count_uncategorized()

    def get_table_for_analysis(
        self,
        service: Literal[
            "credit_cards", "banks", "cash", "manual_investments"
        ] = Services.CREDIT_CARD.value,
        include_split_parents: bool = False,
    ) -> pd.DataFrame:
        """
        Get a service's transaction table with split transactions expanded.

        Split rows replace their parent transaction rows by default. When
        ``include_split_parents`` is ``True``, parent rows are retained and
        marked with ``type = "split_parent"`` so callers can exclude them
        from amount calculations while still displaying them.

        Parameters
        ----------
        service : {"credit_cards", "banks", "cash", "manual_investments"}
            Service whose transaction table to return.
        include_split_parents : bool, optional
            When ``True``, include parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        pd.DataFrame
            Transactions with splits expanded, limited to the canonical
            analysis column set.
        """
        df = self.transactions_repository.get_table(
            service, include_split_parents=include_split_parents
        ).copy()

        analysis_cols = [
            TransactionsTableFields.ID.value,
            TransactionsTableFields.DATE.value,
            TransactionsTableFields.PROVIDER.value,
            TransactionsTableFields.ACCOUNT_NAME.value,
            TransactionsTableFields.ACCOUNT_NUMBER.value,
            TransactionsTableFields.DESCRIPTION.value,
            TransactionsTableFields.AMOUNT.value,
            TransactionsTableFields.CATEGORY.value,
            TransactionsTableFields.TAG.value,
            TransactionsTableFields.UNIQUE_ID.value,
            TransactionsTableFields.SOURCE.value,
            TransactionsTableFields.SPLIT_ID.value,
            TransactionsTableFields.TYPE.value,
        ]

        # The repository only synthesises `split_id` when split children are
        # present; give every frame the column so callers can key on it.
        if TransactionsTableFields.SPLIT_ID.value not in df.columns:
            df[TransactionsTableFields.SPLIT_ID.value] = _empty_split_id(df.index)

        return (
            df[analysis_cols].reset_index(drop=True)
            if all(c in df.columns for c in analysis_cols)
            else df
        )
