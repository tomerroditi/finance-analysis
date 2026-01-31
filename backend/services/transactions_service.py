"""
Transactions service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for transaction operations.
"""

from datetime import datetime, timedelta
from typing import List, Literal, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.naming_conventions import (
    Banks,
    CreditCards,
    IncomeCategories,
    InvestmentCategories,
    LiabilitiesCategories,
    NonExpensesCategories,
    Services,
    SplitTransactionsTableFields,
    TransactionsTableFields,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.transactions_repository import (
    CashTransaction,
    ManualInvestmentTransaction,
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
        self, id_: str, category: str | None, tag: str | None
    ) -> None:
        """Update the category and tag for a transaction by ID."""
        self.transactions_repository.cc_repo.update_tagging_by_id(id_, category, tag)
        self.transactions_repository.bank_repo.update_tagging_by_id(id_, category, tag)
        self.transactions_repository.cash_repo.update_tagging_by_id(id_, category, tag)

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
        return self.transactions_repository.cash_repo.delete_transaction_by_id(
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
