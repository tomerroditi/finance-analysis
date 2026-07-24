"""
Transactions service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for transaction operations.
"""

from datetime import datetime, timedelta
from typing import List, Literal, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    PROTECTED_TAGS,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories
)
from backend.constants.providers import Services
from backend.constants.tables import (
    SplitTransactionsTableFields,
    Tables,
    TransactionsTableFields,
)
from backend.services.transaction_classification import (
    INCOME_CATEGORY_VALUES,
    NON_EXPENSE_BASE_CATEGORIES,
)
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.transactions_repository import (
    CashTransaction,
    ManualInvestmentTransaction,
    ManualTransactionDTO,
    TransactionsRepository,
)
from backend.utils.session_cache import session_cache_get, session_cache_set


class TransactionsService:
    """
    Service for transaction business logic.

    Coordinates between TransactionsRepository and SplitTransactionsRepository
    to provide transaction operations with split handling.
    """

    ANALYSIS_COLUMNS: List[str] = [
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

    def __init__(self, db: Session):
        """
        Initialize the transactions service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.transactions_repository = TransactionsRepository(db)
        self.split_transactions_repository = SplitTransactionsRepository(db)
        self.balance_repo = BankBalanceRepository(db)
        self.investments_repo = InvestmentsRepository(db)

    def get_table_columns_for_display(self) -> List[str]:
        """
        Get the ordered list of column names used for display purposes.

        Returns
        -------
        list[str]
            Column name strings from ``TransactionsTableFields`` in the
            canonical display order.
        """
        return [
            TransactionsTableFields.PROVIDER.value,
            TransactionsTableFields.ACCOUNT_NAME.value,
            TransactionsTableFields.ACCOUNT_NUMBER.value,
            TransactionsTableFields.DATE.value,
            TransactionsTableFields.DESCRIPTION.value,
            TransactionsTableFields.AMOUNT.value,
            TransactionsTableFields.CATEGORY.value,
            TransactionsTableFields.TAG.value,
            TransactionsTableFields.ID.value,
            TransactionsTableFields.STATUS.value,
            TransactionsTableFields.TYPE.value,
            TransactionsTableFields.UNIQUE_ID.value,
            TransactionsTableFields.SOURCE.value,
        ]

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

        cc_data = self.get_table_for_analysis(Services.CREDIT_CARD.value, include_split_parents)
        bank_data = self.get_table_for_analysis(Services.BANK.value, include_split_parents)
        cash_data = self.get_table_for_analysis(Services.CASH.value, include_split_parents)
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

        rows = []
        for _, bal in balances_df.iterrows():
            if bal["prior_wealth_amount"] == 0:
                continue
            rows.append({
                TransactionsTableFields.ID.value: f"bank_pw_{bal['id']}",
                TransactionsTableFields.DATE.value: bal.get("last_manual_update") or bal.get("created_at", ""),
                TransactionsTableFields.PROVIDER.value: bal["provider"],
                TransactionsTableFields.ACCOUNT_NAME.value: bal["account_name"],
                TransactionsTableFields.ACCOUNT_NUMBER.value: None,
                TransactionsTableFields.DESCRIPTION.value: f"Prior Wealth ({bal['provider']} - {bal['account_name']})",
                TransactionsTableFields.AMOUNT.value: bal["prior_wealth_amount"],
                TransactionsTableFields.CATEGORY.value: IncomeCategories.OTHER_INCOME.value,
                TransactionsTableFields.TAG.value: PRIOR_WEALTH_TAG,
                TransactionsTableFields.UNIQUE_ID.value: f"bank_pw_{bal['id']}",
                TransactionsTableFields.SOURCE.value: "bank_balances",
                TransactionsTableFields.SPLIT_ID.value: None,
                TransactionsTableFields.TYPE.value: "normal",
            })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _build_investment_prior_wealth_rows(self) -> pd.DataFrame:
        """Build synthetic prior wealth rows from Investment.prior_wealth_amount.

        Mirrors _build_bank_prior_wealth_rows for bank accounts.
        Only includes open (non-closed) investments with prior_wealth_amount != 0.
        """
        investments_df = self.investments_repo.get_all_investments(include_closed=False)
        if investments_df.empty:
            return pd.DataFrame()

        rows = []
        for _, inv in investments_df.iterrows():
            if inv["prior_wealth_amount"] == 0:
                continue
            rows.append({
                TransactionsTableFields.ID.value: f"inv_pw_{inv['id']}",
                TransactionsTableFields.DATE.value: inv.get("created_date", ""),
                TransactionsTableFields.PROVIDER.value: Services.MANUAL_INVESTMENTS.value,
                TransactionsTableFields.ACCOUNT_NAME.value: inv["name"],
                TransactionsTableFields.ACCOUNT_NUMBER.value: None,
                TransactionsTableFields.DESCRIPTION.value: f"Prior Wealth ({inv['name']})",
                TransactionsTableFields.AMOUNT.value: inv["prior_wealth_amount"],
                TransactionsTableFields.CATEGORY.value: IncomeCategories.OTHER_INCOME.value,
                TransactionsTableFields.TAG.value: PRIOR_WEALTH_TAG,
                TransactionsTableFields.UNIQUE_ID.value: f"inv_pw_{inv['id']}",
                TransactionsTableFields.SOURCE.value: "investments",
                TransactionsTableFields.SPLIT_ID.value: None,
                TransactionsTableFields.TYPE.value: "normal",
            })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)


    def update_tagging_by_id(
        self, table_name: str, unique_id: int, category: str | None, tag: str | None
    ) -> None:
        """
        Update the category and tag for a transaction identified by table and ID.

        Parameters
        ----------
        table_name : str
            Name of the source table (e.g. ``"credit_card_transactions"``).
        unique_id : int
            Unique ID of the transaction to update.
        category : str or None
            New category value. Empty strings are normalised to ``None``.
        tag : str or None
            New tag value. Empty strings are normalised to ``None``.

        Raises
        ------
        ValueError
            If ``table_name`` does not match any known transaction table.
        """
        category = self._normalize_empty_string(category)
        tag = self._normalize_empty_string(tag)
        if table_name == Tables.CREDIT_CARD.value:
            self.transactions_repository.cc_repo.update_tagging_by_unique_id(
                unique_id, category, tag
            )
        elif table_name == Tables.BANK.value:
            self.transactions_repository.bank_repo.update_tagging_by_unique_id(
                unique_id, category, tag
            )
        elif table_name == Tables.CASH.value:
            self.transactions_repository.cash_repo.update_tagging_by_unique_id(
                unique_id, category, tag
            )
        elif table_name == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value:
            self.transactions_repository.manual_investments_repo.update_tagging_by_unique_id(
                unique_id, category, tag
            )
        else:
            raise ValueError(f"Invalid table name: {table_name}")

    def get_transactions_by_tag(
        self, category: str, tag: Optional[str] = None
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

    def get_all_transactions(
        self, service: Literal["credit_cards", "banks", "cash"]
    ) -> pd.DataFrame:
        """
        Get all transactions for the specified service.

        Parameters
        ----------
        service : {"credit_cards", "banks", "cash"}
            Service whose transaction table to return.

        Returns
        -------
        pd.DataFrame
            All transactions from the requested service table.

        Raises
        ------
        ValueError
            If ``service`` is not one of the supported values.
        """
        valid = [Services.CREDIT_CARD.value, Services.BANK.value, Services.CASH.value]
        if service not in valid:
            raise ValueError(
                f"service must be one of {valid}. Got '{service}'"
            )
        return self.transactions_repository.get_table(service)

    def get_merged_transactions(
        self,
        service: Optional[str] = None,
        include_split_parents: bool = False,
        exclude_services: Optional[list[str]] = None,
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
        ValueError
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
        ValueError
            If the source is unknown or no transaction matches.
        """
        return self.transactions_repository.get_transaction_by_id(
            transaction_id, source
        )

    @staticmethod
    def _normalize_empty_string(value: str | None) -> str | None:
        """Convert empty strings to None for category/tag fields."""
        return None if value == "" else value

    def create_transaction(self, data: dict, service: str) -> None:
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
        ValueError
            If service is not 'cash' or 'manual_investments'.
        RuntimeError
            If the transaction could not be created.
        """
        if service not in [Services.CASH.value, Services.MANUAL_INVESTMENTS.value]:
            raise ValueError("Can only create cash or manual_investments transactions")

        # For cash transactions, always set provider to "CASH"
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
        success = self.transactions_repository.add_transaction(tx, service)
        if not success:
            raise RuntimeError("Failed to create transaction")

        if service == Services.CASH.value:
            # Recalculate cash balance if this is a cash transaction
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(data["account_name"])
        elif service == Services.MANUAL_INVESTMENTS.value:
            category = data.get("category")
            tag = data.get("tag")
            if category and tag:
                from backend.services.investments_service import InvestmentsService
                InvestmentsService(self.db).recalculate_prior_wealth_by_tag(category, tag)

    def _filter_updates_for_source(self, source: str, updates: dict) -> dict:
        """Apply per-source permission rules and normalization to an update dict.

        Manual sources (cash, manual investments) may edit date/account_name/
        description/amount (and provider — forced to "CASH" for cash rows);
        scraped sources may only edit category/tag. Empty category/tag strings
        are normalised to ``None``.

        Parameters
        ----------
        source : str
            Source table name.
        updates : dict
            Raw requested updates.

        Returns
        -------
        dict
            The subset of ``updates`` this source is allowed to write.
        """
        is_manual = source in [
            Tables.CASH.value,
            Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        ]
        filtered_updates: dict = {}
        if is_manual:
            if updates.get("date") is not None:
                filtered_updates["date"] = updates["date"]
            if updates.get("account_name") is not None:
                filtered_updates["account_name"] = updates["account_name"]
            if updates.get("description") is not None:
                filtered_updates["description"] = updates["description"]
            if updates.get("amount") is not None:
                filtered_updates["amount"] = updates["amount"]
            # For cash transactions, always set provider to "CASH"
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
        self, unique_id: int, source: str, updates: dict
    ) -> bool:
        """
        Update a transaction with source-based permission constraints.

        Manual sources (``cash``, ``manual_investment_transactions``) may edit
        ``description``, ``amount``, ``provider``, ``date``, and
        ``account_name`` in addition to ``category`` and ``tag``. Scraped
        sources can only update ``category`` and ``tag``. When
        ``account_name`` changes on a cash transaction, balances are
        recalculated for both the old and new account. Empty strings in
        category/tag are normalised to ``None``.

        Parameters
        ----------
        unique_id : int
            Unique ID of the transaction to update.
        source : str
            Source table name (e.g. ``"cash"``, ``"credit_card_transactions"``).
        updates : dict
            Fields to update. Recognised keys: ``description``, ``amount``,
            ``provider``, ``date``, ``account_name``, ``category``, ``tag``.

        Returns
        -------
        bool
            ``True`` if updates were applied, ``False`` if no applicable fields
            were provided.
        """
        from sqlalchemy import select

        target_repo = self.transactions_repository.get_repo_by_source(source)

        # Capture old account_name before updating — needed to recalculate the
        # old account's balance when account_name changes on a cash transaction.
        old_account_name: str | None = None
        if source == Tables.CASH.value and updates.get("account_name") is not None:
            tx_before = self.transactions_repository.db.execute(
                select(target_repo.model).where(
                    target_repo.model.unique_id == unique_id
                )
            ).scalar_one_or_none()
            if tx_before:
                old_account_name = getattr(tx_before, "account_name", None)

        filtered_updates = self._filter_updates_for_source(source, updates)

        if not filtered_updates:
            return False

        result = target_repo.update_transaction_by_unique_id(unique_id, filtered_updates)

        # Recalculate cash balance(s) when a cash transaction is updated.
        if result and source == Tables.CASH.value:
            from backend.services.cash_balance_service import CashBalanceService
            cash_balance_svc = CashBalanceService(self.db)

            new_account_name = filtered_updates.get("account_name")
            if new_account_name and old_account_name and new_account_name != old_account_name:
                # account_name changed: recalculate both old and new accounts.
                cash_balance_svc.recalculate_current_balance(old_account_name)
                cash_balance_svc.recalculate_current_balance(new_account_name)
            else:
                # No account change: recalculate the current account.
                tx_record = self.transactions_repository.db.execute(
                    select(target_repo.model).where(
                        target_repo.model.unique_id == unique_id
                    )
                ).scalar_one_or_none()
                if tx_record:
                    account_name = getattr(tx_record, "account_name", None)
                    if account_name:
                        cash_balance_svc.recalculate_current_balance(account_name)

        return result

    def delete_transaction(self, unique_id: int, source: str) -> None:
        """
        Delete a transaction with source validation and protection checks.

        Only ``cash_transactions`` and ``manual_investment_transactions`` sources
        are deletable. System-generated Prior Wealth transactions (identified by
        matching tag and account name) are protected and cannot be deleted.
        After deletion, the cash prior-wealth offset or investment prior-wealth
        is recalculated as needed.

        Parameters
        ----------
        unique_id : int
            Unique ID of the transaction to delete.
        source : str
            Source table name; must be ``"cash_transactions"`` or
            ``"manual_investment_transactions"``.

        Raises
        ------
        PermissionError
            If the source does not allow deletion or the transaction is a
            protected system-generated record.
        ValueError
            If the transaction is not found or deletion fails.
        """
        if source not in [Tables.CASH.value, Tables.MANUAL_INVESTMENT_TRANSACTIONS.value]:
            raise PermissionError(
                f"Deletion of {source} transactions is prohibited"
            )

        target_repo = self.transactions_repository.get_repo_by_source(source)

        from sqlalchemy import select

        tx_record = self.transactions_repository.db.execute(
            select(target_repo.model).where(
                target_repo.model.unique_id == unique_id
            )
        ).scalar_one_or_none()

        if not tx_record:
            raise ValueError("Transaction not found")

        tag = getattr(tx_record, "tag", None)
        account_name = getattr(tx_record, "account_name", None)
        if tag in PROTECTED_TAGS and account_name in PROTECTED_TAGS:
            raise PermissionError(
                f"Cannot manually delete system-generated {tag} transaction"
            )

        inv_category = None
        inv_tag = None
        if source == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value:
            inv_category = getattr(tx_record, "category", None)
            inv_tag = getattr(tx_record, "tag", None)

        success = target_repo.delete_transaction_by_unique_id(unique_id)
        if not success:
            raise ValueError("Transaction not found or deletion failed")

        self._purge_dependent_records(unique_id, source)

        if source == Tables.CASH.value:
            # Recalculate cash balance if this was a cash transaction
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(account_name)
        elif source == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value and inv_category and inv_tag:
            from backend.services.investments_service import InvestmentsService
            InvestmentsService(self.db).recalculate_prior_wealth_by_tag(inv_category, inv_tag)

    def _purge_dependent_records(self, unique_id: int, source: str) -> None:
        """
        Remove every record that pointed at a now-deleted transaction.

        Splits, pending refunds (and their links), refund-source notes and
        budget month overrides all reference a transaction by
        ``(source_table, unique_id)``. ``unique_id`` is a per-table
        auto-increment and SQLite reuses rowids, so an orphan left behind is
        not merely dead data — the next transaction created in that table
        silently inherits it, landing in the wrong budget month or carrying
        someone else's refund.

        Parameters
        ----------
        unique_id : int
            unique_id of the deleted transaction.
        source : str
            Table name the transaction was deleted from.
        """
        from backend.repositories.budget_month_override_repository import (
            BudgetMonthOverrideRepository,
        )
        from backend.repositories.pending_refunds_repository import (
            PendingRefundsRepository,
        )

        # Older rows may store the service name ("cash") rather than the table
        # name ("cash_transactions"); accept every spelling that resolves here.
        aliases = {
            name
            for name, repo in self.transactions_repository.repo_map.items()
            if repo.model.__tablename__ == source
        }
        aliases.add(source)
        source_aliases = sorted(aliases)

        self.transactions_repository.split_repo.delete_all_splits_for_transaction(
            unique_id, source
        )

        PendingRefundsRepository(self.db).delete_for_transaction(
            source_aliases, unique_id
        )

        override_repo = BudgetMonthOverrideRepository(self.db)
        for alias in source_aliases:
            override_repo.delete_for_source("transaction", unique_id, alias)

    def split_transaction(
        self, unique_id: int, source: str, splits: list[dict]
    ) -> None:
        """Split a transaction into multiple partial amounts across categories.

        Wraps the repository operation so the route layer never reaches into
        repositories directly.

        Parameters
        ----------
        unique_id : int
            Unique ID of the transaction to split.
        source : str
            Source table name (e.g. ``"bank_transactions"``).
        splits : list[dict]
            One entry per resulting split, each with ``amount``, ``category``,
            ``tag``.

        Raises
        ------
        ValueError
            If the source is not recognized or the split fails to commit.
        """
        success = self.transactions_repository.split_transaction(
            unique_id, source, splits
        )
        if not success:
            raise ValueError("Failed to split transaction")

    def revert_split(self, unique_id: int, source: str) -> None:
        """Revert a split transaction back to a normal transaction.

        Parameters
        ----------
        unique_id : int
            Unique ID of the split-parent transaction to revert.
        source : str
            Source table name (e.g. ``"bank_transactions"``).

        Raises
        ------
        ValueError
            If the source is not recognized or the revert fails to commit.
        """
        success = self.transactions_repository.revert_split(unique_id, source)
        if not success:
            raise ValueError("Failed to revert split")

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
    ) -> None:
        """
        Apply the same category, tag, and optional fields to multiple transactions.

        For manual sources (``cash``, ``manual_investment_transactions``),
        ``description``, ``account_name``, ``date``, and ``amount`` are also
        applied when provided. Permission checks and side effects (e.g. cash
        balance recalculation) are handled by ``update_transaction``.

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
        """
        from sqlalchemy import select, update

        updates: dict = {
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

        repo = self.transactions_repository.get_repo_by_source(source)
        if repo is None:
            raise ValueError(f"Invalid source: '{source}'")

        filtered_updates = self._filter_updates_for_source(source, updates)
        if not filtered_updates or not transaction_ids:
            return

        ids = [int(uid) for uid in transaction_ids]

        # Collect affected cash accounts BEFORE the update — the old account
        # names matter when account_name itself is being changed.
        affected_accounts: set[str] = set()
        if source == Tables.CASH.value:
            rows = (
                self.db.execute(
                    select(repo.model.account_name).where(
                        repo.model.unique_id.in_(ids)
                    )
                )
                .scalars()
                .all()
            )
            affected_accounts.update(a for a in rows if a)
            if filtered_updates.get("account_name"):
                affected_accounts.add(filtered_updates["account_name"])

        # One UPDATE ... WHERE unique_id IN (...) and one commit instead of a
        # commit (plus a cash-balance recalculation) per row.
        self.db.execute(
            update(repo.model)
            .where(repo.model.unique_id.in_(ids))
            .values(**filtered_updates)
        )
        self.db.commit()

        if affected_accounts:
            from backend.services.cash_balance_service import CashBalanceService

            cash_balance_svc = CashBalanceService(self.db)
            for account in sorted(affected_accounts):
                cash_balance_svc.recalculate_current_balance(account)

    def get_untagged_transactions(
        self,
        service: Literal["credit_cards", "banks"],
        account_number: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get transactions that have no category assigned.

        Parameters
        ----------
        service : {"credit_cards", "banks"}
            Service to query.
        account_number : str, optional
            For bank transactions, further filter by account number.
            Ignored for credit card transactions.

        Returns
        -------
        pd.DataFrame
            Transactions where the ``category`` column is ``NaN`` / ``None``.
        """
        transactions = self.transactions_repository.get_table(service)
        category_col = TransactionsTableFields.CATEGORY.value
        untagged = transactions[transactions[category_col].isna()]

        if account_number and service == Services.BANK.value:
            account_col = TransactionsTableFields.ACCOUNT_NUMBER.value
            untagged = untagged[untagged[account_col] == account_number]

        return untagged

    def get_latest_data_date(self) -> datetime:
        """
        Get the minimum of the latest transaction dates across all tables.

        Returns the minimum so that the displayed "latest date" reflects the
        most outdated source (i.e. all sources have data up to at least this date).

        Returns
        -------
        datetime
            The minimum latest-date across all tables. Falls back to
            365 days ago for tables with no data.
        """
        latest_dates = []
        tables = self.transactions_repository.get_all_table_names()

        for table in tables:
            latest_date = self.transactions_repository.get_latest_date_from_table(table)
            if latest_date is not None:
                latest_dates.append(latest_date)
            else:
                latest_dates.append(datetime.today() - timedelta(days=365))

        return (
            min(latest_dates)
            if latest_dates
            else datetime.today() - timedelta(days=365)
        )

    def count_uncategorized(self) -> int:
        """Count uncategorized transactions in the merged non-insurance view.

        Returns
        -------
        int
            Number of transactions with no category, an empty category, or
            the literal ``"Uncategorized"`` category.
        """
        return self.transactions_repository.count_uncategorized()

    def get_earliest_data_date(self) -> datetime:
        """
        Get the earliest transaction date across all tables.

        Returns
        -------
        datetime
            The minimum date found across all transaction tables.
            Falls back to ``datetime.now()`` if no data exists.
        """
        earliest_dates = []
        tables = self.transactions_repository.get_all_table_names()

        for table in tables:
            earliest_date = self.transactions_repository.get_earliest_date_from_table(
                table
            )
            if earliest_date is not None:
                earliest_dates.append(earliest_date)

        # Fallback if no data exists
        return min(earliest_dates) if earliest_dates else datetime.now()

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
        df = self.transactions_repository.get_table(service).copy()

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

        split_df = self.split_transactions_repository.get_data()
        if split_df.empty:
            if TransactionsTableFields.SPLIT_ID.value not in df.columns:
                df[TransactionsTableFields.SPLIT_ID.value] = None
            return (
                df[analysis_cols] if all(c in df.columns for c in analysis_cols) else df
            )

        _repo = self.transactions_repository.get_repo_by_source(service)
        source_table = _repo.model.__tablename__ if _repo is not None else ""
        split_df = split_df[
            (split_df[SplitTransactionsTableFields.SOURCE.value] == source_table)
            & split_df[SplitTransactionsTableFields.TRANSACTION_ID.value].isin(
                df[TransactionsTableFields.UNIQUE_ID.value]
            )
        ]
        split_ids = set(split_df[SplitTransactionsTableFields.TRANSACTION_ID.value])
        mask = df[TransactionsTableFields.UNIQUE_ID.value].isin(split_ids)

        if include_split_parents:
            # Include parent transactions alongside split children
            base_df = df.copy()
            base_df[TransactionsTableFields.SPLIT_ID.value] = None
            # Mark parent transactions with type 'split_parent' for identification
            base_df.loc[mask, "type"] = "split_parent"
        else:
            # Exclude parent transactions (default behavior)
            base_df = df[~mask].copy()
            base_df[TransactionsTableFields.SPLIT_ID.value] = None

        split_rows = []
        for id_, split_group in split_df.groupby(
            SplitTransactionsTableFields.TRANSACTION_ID.value
        ):
            orig_row = df[df[TransactionsTableFields.UNIQUE_ID.value] == id_]
            if orig_row.empty:
                continue
            for _, split in split_group.iterrows():
                split_row = orig_row.copy()
                split_row[TransactionsTableFields.AMOUNT.value] = split[
                    SplitTransactionsTableFields.AMOUNT.value
                ]
                split_row[TransactionsTableFields.CATEGORY.value] = split[
                    SplitTransactionsTableFields.CATEGORY.value
                ]
                split_row[TransactionsTableFields.TAG.value] = split[
                    SplitTransactionsTableFields.TAG.value
                ]
                split_row[TransactionsTableFields.SPLIT_ID.value] = split[
                    SplitTransactionsTableFields.ID.value
                ]
                split_rows.append(split_row)

        if split_rows:
            split_rows_df = pd.concat(split_rows, ignore_index=True)
            result_df = pd.concat([base_df, split_rows_df], ignore_index=True)
        else:
            result_df = base_df
            if TransactionsTableFields.SPLIT_ID.value not in result_df.columns:
                result_df[TransactionsTableFields.SPLIT_ID.value] = None

        return (
            result_df[analysis_cols].reset_index(drop=True)
            if all(c in result_df.columns for c in analysis_cols)
            else result_df
        )

