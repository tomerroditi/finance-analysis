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
from backend.constants.providers import Banks, CreditCards, Services
from backend.constants.tables import (
    SplitTransactionsTableFields,
    Tables,
    TransactionsTableFields,
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


class TransactionsService:
    """
    Service for transaction business logic.

    Coordinates between TransactionsRepository and SplitTransactionsRepository
    to provide transaction operations with split handling.
    """

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

    def add_transaction(
        self, transaction: dict, service: Literal["cash", "manual_investments"]
    ) -> bool:
        """
        Add a new transaction to the specified service table.

        Parameters
        ----------
        transaction : dict
            A dictionary representing the transaction to add.
        service : Literal['cash', 'manual_investments']
            The service to which the transaction belongs.

        Returns
        -------
        bool
            True if the transaction was added successfully, False otherwise.
        """
        if service == "cash":
            tx = CashTransaction(**transaction)
        elif service == "manual_investments":
            tx = ManualInvestmentTransaction(**transaction)
        else:
            raise ValueError(
                "Only 'cash' and 'manual_investments' services are supported."
            )

        return self.transactions_repository.add_transaction(tx, service)

    def sync_prior_wealth_offset(
        self, target_service: Literal["cash"] | None = None
    ) -> None:
        """
        Synchronize the prior wealth offset transaction for the cash service.

        Tracks manual deposits (negative amounts) for cash and maintains a single
        consolidated "Prior Wealth" transaction in the cash table.
        Investment prior wealth is handled separately via Investment.prior_wealth_amount
        and _build_investment_prior_wealth_rows().

        Logic per service:
        1. Calculate total offset needed = sum(abs(manual_deposits)) for that service
        2. Find existing offset transaction in that service's table
        3. If total > 0: Update or Create single offset transaction
        4. If total == 0: Delete existing offset transaction(s)
        """
        services_to_sync = (
            [target_service]
            if target_service
            else [Services.CASH.value]
        )

        for service in services_to_sync:
            # 1. Get transactions for this service
            df = self.transactions_repository.get_table(service=service)

            # 2. Calculate offset needed (sum of manual negative amounts)
            offset_needed = 0.0
            if not df.empty:
                # Filter: Amount < 0 AND Tag != PRIOR_WEALTH_TAG (to exclude the offset itself)
                amount_col = TransactionsTableFields.AMOUNT.value
                tag_col = TransactionsTableFields.TAG.value

                mask = df[amount_col] < 0
                if tag_col in df.columns:
                    mask = mask & (df[tag_col] != PRIOR_WEALTH_TAG)

                offset_needed = abs(df.loc[mask, amount_col].sum())

            # 3. Handle offset transaction in the specific service table
            if service == Services.CASH.value:
                repo = self.transactions_repository.cash_repo
            else:
                raise ValueError(
                    f"Service '{service}' not supported for prior wealth offset"
                )

            current_data = repo.get_table()
            existing_offsets = pd.DataFrame()

            if not current_data.empty:
                offset_mask = (
                    (
                        current_data[TransactionsTableFields.TAG.value]
                        == PRIOR_WEALTH_TAG
                    )
                    & (
                        current_data[TransactionsTableFields.CATEGORY.value]
                        == IncomeCategories.OTHER_INCOME.value
                    )
                    & (
                        current_data[TransactionsTableFields.ACCOUNT_NAME.value]
                        == PRIOR_WEALTH_TAG
                    )
                )
                existing_offsets = current_data[offset_mask]

            if offset_needed > 0:
                if not existing_offsets.empty:
                    # Update first existing one
                    first_id = existing_offsets.iloc[0][
                        TransactionsTableFields.UNIQUE_ID.value
                    ]
                    target_date = self.get_earliest_data_date()
                    repo.update_transaction_by_unique_id(
                        first_id,
                        {
                            "amount": offset_needed,
                            "date": target_date.strftime("%Y-%m-%d"),
                        },
                    )
                    # Delete duplicates if any
                    if len(existing_offsets) > 1:
                        for _, row in existing_offsets.iloc[1:].iterrows():
                            repo.delete_transaction_by_unique_id(
                                str(row[TransactionsTableFields.UNIQUE_ID.value])
                            )
                else:
                    target_date = self.get_earliest_data_date()
                    offset_tx = ManualTransactionDTO(
                        date=target_date,
                        account_name=PRIOR_WEALTH_TAG,
                        description=f"Prior Wealth Offset ({service})",
                        amount=offset_needed,
                        provider="MANUAL",
                        account_number="prior_wealth",
                        category=IncomeCategories.OTHER_INCOME.value,
                        tag=PRIOR_WEALTH_TAG,
                    )
                    self.transactions_repository.add_transaction(offset_tx, service)
            else:
                # Delete all existing offsets if amount needed is 0
                if not existing_offsets.empty:
                    for _, row in existing_offsets.iterrows():
                        repo.delete_transaction_by_unique_id(
                            str(row[TransactionsTableFields.UNIQUE_ID.value])
                        )

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
        cc_data = self.get_table_for_analysis("credit_cards", include_split_parents)
        bank_data = self.get_table_for_analysis("banks", include_split_parents)
        cash_data = self.get_table_for_analysis("cash", include_split_parents)
        manual_investments_data = self.get_table_for_analysis(
            "manual_investments", include_split_parents
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
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)

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
                TransactionsTableFields.PROVIDER.value: "manual_investments",
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

    def update_transaction_by_id(self, transaction_id: str, updates: dict) -> bool:
        """
        Update a transaction by ID, searching across CC, bank, and cash tables.

        Parameters
        ----------
        transaction_id : str
            Transaction ID to search for across tables.
        updates : dict
            Field names and new values to apply.

        Returns
        -------
        bool
            ``True`` if the transaction was found and updated in at least one table.
        """
        cc_res = self.transactions_repository.cc_repo.update_transaction_by_unique_id(
            transaction_id, updates
        )
        bank_res = self.transactions_repository.bank_repo.update_transaction_by_unique_id(
            transaction_id, updates
        )
        cash_res = self.transactions_repository.cash_repo.update_transaction_by_unique_id(
            transaction_id, updates
        )
        return cc_res or bank_res or cash_res

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
        if service not in ["credit_cards", "banks", "cash"]:
            raise ValueError(
                f"service must be one of 'credit_cards', 'banks', 'cash'. Got '{service}'"
            )
        return self.transactions_repository.get_table(service)

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
        if service not in ["cash", "manual_investments"]:
            raise ValueError("Can only create cash or manual_investments transactions")

        # For cash transactions, always set provider to "CASH"
        provider = "CASH" if service == "cash" else data.get("provider")

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

        if service == "cash":
            # Recalculate cash balance if this is a cash transaction
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(data["account_name"])
        elif service == "manual_investments":
            category = data.get("category")
            tag = data.get("tag")
            if category and tag:
                from backend.services.investments_service import InvestmentsService
                InvestmentsService(self.db).recalculate_prior_wealth_by_tag(category, tag)

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
        is_manual = source in ["cash_transactions", "manual_investment_transactions"]

        # Capture old account_name before updating — needed to recalculate the
        # old account's balance when account_name changes on a cash transaction.
        old_account_name: str | None = None
        if source == "cash_transactions" and updates.get("account_name") is not None:
            tx_before = self.transactions_repository.db.execute(
                select(target_repo.model).where(
                    target_repo.model.unique_id == unique_id
                )
            ).scalar_one_or_none()
            if tx_before:
                old_account_name = getattr(tx_before, "account_name", None)

        filtered_updates = {}
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
            if source == "cash_transactions":
                filtered_updates["provider"] = "CASH"
            elif updates.get("provider") is not None:
                filtered_updates["provider"] = updates["provider"]

        if updates.get("category") is not None:
            filtered_updates["category"] = self._normalize_empty_string(
                updates["category"]
            )
        if updates.get("tag") is not None:
            filtered_updates["tag"] = self._normalize_empty_string(updates["tag"])

        if not filtered_updates:
            return False

        result = target_repo.update_transaction_by_unique_id(unique_id, filtered_updates)

        # Recalculate cash balance(s) when a cash transaction is updated.
        if result and source == "cash_transactions":
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
        if source not in ["cash_transactions", "manual_investment_transactions"]:
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
        if source == "manual_investment_transactions":
            inv_category = getattr(tx_record, "category", None)
            inv_tag = getattr(tx_record, "tag", None)

        success = target_repo.delete_transaction_by_unique_id(unique_id)
        if not success:
            raise ValueError("Transaction not found or deletion failed")

        if source == "cash_transactions":
            # Recalculate cash balance if this was a cash transaction
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(account_name)
        elif source == "manual_investment_transactions" and inv_category and inv_tag:
            from backend.services.investments_service import InvestmentsService
            InvestmentsService(self.db).recalculate_prior_wealth_by_tag(inv_category, inv_tag)

    def bulk_tag_transactions(
        self,
        transaction_ids: list[int],
        source: str,
        category: str | None,
        tag: str | None,
        description: str | None = None,
        account_name: str | None = None,
        date: str | None = None,
    ) -> None:
        """
        Apply the same category, tag, and optional fields to multiple transactions.

        For manual sources (``cash``, ``manual_investment_transactions``),
        ``description``, ``account_name``, and ``date`` are also applied when
        provided. Permission checks and side effects (e.g. cash balance
        recalculation) are handled by ``update_transaction``.

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
        """
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

        for uid in transaction_ids:
            self.update_transaction(uid, source, updates)

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

        if account_number and service == "banks":
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
        ] = "credit_cards",
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

        split_df = split_df[
            split_df[SplitTransactionsTableFields.TRANSACTION_ID.value].isin(
                df[TransactionsTableFields.ID.value]
            )
        ]
        split_ids = set(split_df[SplitTransactionsTableFields.TRANSACTION_ID.value])
        mask = df[TransactionsTableFields.ID.value].isin(split_ids)

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
            orig_row = df[df[TransactionsTableFields.ID.value] == id_]
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

    def get_kpis(self, df: pd.DataFrame) -> dict:
        """
        Calculate key financial KPIs from a transactions DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame (typically from ``get_data_for_analysis``).

        Returns
        -------
        dict
            Dictionary with keys:

            - ``income`` – total income.
            - ``expenses`` – total expenses (absolute value).
            - ``savings_and_investments`` – total invested (absolute value).
            - ``bank_balance_increase`` – income minus expenses minus debt payments minus investments.
            - ``savings_rate`` – ``(bank_balance_increase + investments) / income * 100``.
            - ``liabilities_paid`` – absolute value of outgoing liability payments.
            - ``liabilities_received`` – incoming liability amounts (loans).
            - ``largest_expense_cat_name`` – category name with highest spend.
            - ``largest_expense_cat_val`` – spend amount for that category.
        """
        data = self.split_data_by_category_types(df)
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value

        period_income = data["income"][amount_col].sum()
        period_expenses = data["expenses"][amount_col].sum() * -1 + 0
        period_investments = data["investments"][amount_col].sum() * -1 + 0
        period_liabilities_paid = (
            data["liabilities"][data["liabilities"][amount_col] < 0][amount_col].sum()
            * -1
            + 0
        )
        period_liabilities_received = data["liabilities"][
            data["liabilities"][amount_col] > 0
        ][amount_col].sum()
        bank_balance_increase = (
            period_income
            - period_expenses
            - period_liabilities_paid
            - period_investments
        )
        total_savings = bank_balance_increase + period_investments
        actual_savings_rate = (
            (total_savings / period_income * 100) if period_income != 0 else 0
        )
        largest_expense_cat = (
            data["expenses"]
            .groupby(category_col)[amount_col]
            .sum()
            .abs()
            .sort_values(ascending=False)
        )
        largest_expense_cat_name = (
            largest_expense_cat.index[0] if not largest_expense_cat.empty else "-"
        )
        largest_expense_cat_val = (
            largest_expense_cat.iloc[0] if not largest_expense_cat.empty else 0
        )

        return {
            "income": period_income,
            "expenses": period_expenses,
            "savings_and_investments": period_investments,
            "bank_balance_increase": bank_balance_increase,
            "savings_rate": actual_savings_rate,
            "liabilities_paid": period_liabilities_paid,
            "liabilities_received": period_liabilities_received,
            "largest_expense_cat_name": largest_expense_cat_name,
            "largest_expense_cat_val": largest_expense_cat_val,
        }

    @staticmethod
    def split_data_by_category_types(df: pd.DataFrame) -> dict:
        """
        Partition a transactions DataFrame into category-type groups.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions DataFrame with a ``category`` column.

        Returns
        -------
        dict
            Dictionary with keys ``expenses``, ``investments``, ``income``,
            and ``liabilities``, each containing the relevant subset of ``df``.
            The ``expenses`` group includes all rows not in any special category.
        """
        category_col = TransactionsTableFields.CATEGORY.value
        income_categories = [e.value for e in IncomeCategories]
        non_expenses_categories = [INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY] + income_categories

        return {
            "expenses": df[~df[category_col].isin(non_expenses_categories)],
            "investments": df[df[category_col] == INVESTMENTS_CATEGORY].copy(),
            "income": df[df[category_col].isin(income_categories)],
            "liabilities": df[df[category_col] == LIABILITIES_CATEGORY].copy(),
        }

    def get_liabilities_summary(self, filtered_df: pd.DataFrame) -> dict:
        """
        Get a liabilities summary with all-time totals and per-tag breakdown.

        All-time totals are computed from the full dataset regardless of
        the date filter applied to ``filtered_df``.

        Parameters
        ----------
        filtered_df : pd.DataFrame
            Date-filtered transactions DataFrame used for the per-tag breakdown.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``total_received`` – all-time total of incoming liability amounts (loans).
            - ``total_paid`` – all-time total paid on liabilities.
            - ``outstanding_balance`` – ``total_received - total_paid``.
            - ``tag_summary`` – DataFrame with columns ``Name``, ``Received``,
              ``Paid``, ``Outstanding Balance`` grouped by tag (from ``filtered_df``).
            - ``filtered_liabilities`` – liability rows from ``filtered_df``.
        """
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value

        all_data = self.get_data_for_analysis()
        all_liabilities = all_data[all_data[category_col] == LIABILITIES_CATEGORY]
        filtered_liabilities = filtered_df[filtered_df[category_col] == LIABILITIES_CATEGORY]

        total_received = all_liabilities[all_liabilities[amount_col] > 0][
            amount_col
        ].sum()
        total_paid = abs(
            all_liabilities[all_liabilities[amount_col] < 0][amount_col].sum()
        )
        net_change = total_received - total_paid

        tag_summary = (
            filtered_liabilities.groupby(tag_col)[amount_col]
            .agg(
                [
                    lambda x: abs(x[x > 0].sum()),
                    lambda x: abs(x[x < 0].sum()),
                    lambda x: abs(x.sum()),
                ]
            )
            .reset_index()
        )
        tag_summary.columns = ["Name", "Received", "Paid", "Outstanding Balance"]

        return {
            "total_received": abs(total_received),
            "total_paid": abs(total_paid),
            "outstanding_balance": abs(net_change),
            "tag_summary": tag_summary,
            "filtered_liabilities": filtered_liabilities,
        }

    @staticmethod
    def get_providers_for_service(
        service: Literal["credit_cards", "banks"],
    ) -> List[str]:
        """
        Get the list of provider identifiers for the specified service.

        Parameters
        ----------
        service : {"credit_cards", "banks"}
            Service type to query.

        Returns
        -------
        list[str]
            Provider enum values for the requested service.

        Raises
        ------
        ValueError
            If ``service`` is not ``"credit_cards"`` or ``"banks"``.
        """
        if service == Services.CREDIT_CARD.value:
            return [e.value for e in CreditCards]
        elif service == Services.BANK.value:
            return [e.value for e in Banks]
        else:
            raise ValueError(
                f"Service must be 'credit_cards' or 'banks'. Got '{service}'"
            )

    @staticmethod
    def get_all_providers() -> List[str]:
        """
        Get the combined list of all provider identifiers across credit cards and banks.

        Returns
        -------
        list[str]
            All credit card provider values followed by all bank provider values.
        """
        return [e.value for e in CreditCards] + [e.value for e in Banks]
