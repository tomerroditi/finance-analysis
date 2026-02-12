"""
Transactions service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for transaction operations.
"""

from datetime import datetime, timedelta
from typing import List, Literal, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.naming_conventions import (
    PRIOR_WEALTH_TAG,
    PROTECTED_TAGS,
    Banks,
    CreditCards,
    IncomeCategories,
    InvestmentCategories,
    LiabilitiesCategories,
    NonExpensesCategories,
    Services,
    SplitTransactionsTableFields,
    Tables,
    TransactionsTableFields,
)
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
        self.transactions_repository = TransactionsRepository(db)
        self.split_transactions_repository = SplitTransactionsRepository(db)

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
        self, target_service: Literal["cash", "manual_investments"] | None = None
    ) -> None:
        """
        Synchronize the prior wealth offset transaction for each service.

        Tracks manual deposits (negative amounts) separately for each service (cash/manual_investments)
        and maintains a single consolidated "Prior Wealth" transaction in EACH table.

        Logic per service:
        1. Calculate total offset needed = sum(abs(manual_deposits)) for that service
        2. Find existing offset transaction in that service's table
        3. If total > 0: Update or Create single offset transaction
        4. If total == 0: Delete existing offset transaction(s)
        """
        services_to_sync = (
            [target_service]
            if target_service
            else [Services.CASH.value, Services.MANUAL_INVESTMENTS.value]
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
            elif service == Services.MANUAL_INVESTMENTS.value:
                repo = self.transactions_repository.manual_investments_repo
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
                    repo.update_transaction_by_id(
                        str(first_id),
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
        """Get the columns of the transactions table."""
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
        """Get table data for analysis purposes."""
        cc_data = self.get_table_for_analysis("credit_cards", include_split_parents)
        bank_data = self.get_table_for_analysis("banks", include_split_parents)
        cash_data = self.get_table_for_analysis("cash", include_split_parents)
        manual_investments_data = self.get_table_for_analysis(
            "manual_investments", include_split_parents
        )
        dfs = [cc_data, bank_data, cash_data, manual_investments_data]
        dfs = [df for df in dfs if not df.empty]
        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)

    def update_tagging_by_id(
        self, table_name: str, unique_id: int, category: str | None, tag: str | None
    ) -> None:
        """Update the category and tag for a transaction by ID."""
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
        """Update a transaction by ID with the given field updates."""
        cc_res = self.transactions_repository.cc_repo.update_transaction_by_id(
            transaction_id, updates
        )
        bank_res = self.transactions_repository.bank_repo.update_transaction_by_id(
            transaction_id, updates
        )
        cash_res = self.transactions_repository.cash_repo.update_transaction_by_id(
            transaction_id, updates
        )
        return cc_res or bank_res or cash_res

    def delete_transaction_by_id(self, transaction_id: str) -> bool:
        """Delete a transaction by ID. Supports cash transactions only."""
        return self.transactions_repository.cash_repo.delete_transaction_by_unique_id(
            transaction_id
        )

    def get_transactions_by_tag(
        self, category: str, tag: Optional[str] = None
    ) -> pd.DataFrame:
        """Get all transactions filtered by category and optionally tag."""
        df = self.get_data_for_analysis()
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        investment_df = df[df[category_col] == category]
        if tag:
            investment_df = investment_df[investment_df[tag_col] == tag]
        return investment_df.reset_index(drop=True)

    def get_all_transactions(
        self, service: Literal["credit_cards", "banks", "cash"]
    ) -> pd.DataFrame:
        """Get all transactions for the specified service."""
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

        tx = ManualTransactionDTO(
            date=datetime.combine(data["date"], datetime.min.time()),
            account_name=data["account_name"],
            description=data["description"],
            amount=data["amount"],
            provider=data.get("provider"),
            account_number=data.get("account_number"),
            category=self._normalize_empty_string(data.get("category")),
            tag=self._normalize_empty_string(data.get("tag")),
        )
        success = self.transactions_repository.add_transaction(tx, service)
        if not success:
            raise RuntimeError("Failed to create transaction")

        self.sync_prior_wealth_offset()

    def update_transaction(
        self, unique_id: int, source: str, updates: dict
    ) -> bool:
        """
        Update a transaction with source-based permission constraints.

        Manual sources (cash, manual_investment_transactions) can edit
        description, amount, and provider. All sources can update category/tag.

        Returns
        -------
        bool
            True if updates were applied, False if no changes were needed.
        """
        target_repo = self.transactions_repository.get_repo_by_source(source)
        is_manual = source in ["cash", "manual_investment_transactions"]

        filtered_updates = {}
        if is_manual:
            if updates.get("description") is not None:
                filtered_updates["description"] = updates["description"]
            if updates.get("amount") is not None:
                filtered_updates["amount"] = updates["amount"]
            if updates.get("provider") is not None:
                filtered_updates["provider"] = updates["provider"]

        if updates.get("category") is not None:
            filtered_updates["category"] = self._normalize_empty_string(
                updates["category"]
            )
        if updates.get("tag") is not None:
            filtered_updates["tag"] = self._normalize_empty_string(updates["tag"])

        if not filtered_updates:
            return False

        return target_repo.update_transaction_by_unique_id(unique_id, filtered_updates)

    def delete_transaction(self, unique_id: int, source: str) -> None:
        """
        Delete a transaction with source and protection checks.

        Raises
        ------
        PermissionError
            If the source does not allow deletion or the transaction is protected.
        ValueError
            If the transaction is not found.
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

        success = target_repo.delete_transaction_by_unique_id(unique_id)
        if not success:
            raise ValueError("Transaction not found or deletion failed")

        self.sync_prior_wealth_offset()

    def bulk_tag_transactions(
        self,
        transaction_ids: list[int],
        source: str,
        category: str | None,
        tag: str | None,
    ) -> None:
        """Apply tagging to multiple transactions of the same source."""
        tx_list = [
            {"unique_id": uid, "source": source} for uid in transaction_ids
        ]
        self.transactions_repository.bulk_update_tagging(
            tx_list,
            self._normalize_empty_string(category),
            self._normalize_empty_string(tag),
        )

    def get_untagged_transactions(
        self,
        service: Literal["credit_cards", "banks"],
        account_number: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get transactions that don't have categories assigned."""
        transactions = self.transactions_repository.get_table(service)
        category_col = TransactionsTableFields.CATEGORY.value
        untagged = transactions[transactions[category_col].isna()]

        if account_number and service == "banks":
            account_col = TransactionsTableFields.ACCOUNT_NUMBER.value
            untagged = untagged[untagged[account_col] == account_number]

        return untagged

    def get_latest_data_date(self) -> datetime:
        """Get the latest date of transactions across all tables."""
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
        """Get the earliest date of transactions across all tables."""
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
        Returns the transactions table with split transactions expanded.

        Split rows replace the original transaction rows unless include_split_parents
        is True, in which case parent transactions are also included.
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
        """Calculate KPIs for the given DataFrame."""
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
        """Split data into expenses, savings, income, and liabilities."""
        category_col = TransactionsTableFields.CATEGORY.value
        investment_categories = [e.value for e in InvestmentCategories]
        income_categories = [e.value for e in IncomeCategories]
        liabilities_categories = [e.value for e in LiabilitiesCategories]
        non_expenses_categories = [e.value for e in NonExpensesCategories]

        return {
            "expenses": df[~df[category_col].isin(non_expenses_categories)],
            "investments": df[df[category_col].isin(investment_categories)].copy(),
            "income": df[df[category_col].isin(income_categories)],
            "liabilities": df[df[category_col].isin(liabilities_categories)],
        }

    def get_liabilities_summary(self, filtered_df: pd.DataFrame) -> dict:
        """Get liabilities summary including totals and per-tag breakdown."""
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        liabilities_categories = [e.value for e in LiabilitiesCategories]

        all_data = self.get_data_for_analysis()
        all_liabilities = all_data[all_data[category_col].isin(liabilities_categories)]
        filtered_liabilities = filtered_df[
            filtered_df[category_col].isin(liabilities_categories)
        ]

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
        """Get a list of providers for the specified service."""
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
        """Get a list of all providers across both services."""
        return [e.value for e in CreditCards] + [e.value for e in Banks]
