from datetime import datetime, timedelta
from typing import List, Literal, Optional

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository
from fad.app.data_access.transactions_repository import TransactionsRepository, CashTransaction, ManualInvestmentTransaction
from fad.app.naming_conventions import (
    TransactionsTableFields,
    NonExpensesCategories,
    SavingsAndInvestmentsCategories,
    IncomeCategories,
    LiabilitiesCategories,
    CreditCards,
    Banks,
    Services
)


class TransactionsService:
    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.transactions_repository = TransactionsRepository(conn)
        self.split_transactions_repository = SplitTransactionsRepository(conn)

    def add_transaction(self, transaction: dict, service: Literal['cash', 'manual_investments']) -> bool:
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
        if service == 'cash':
            transaction = CashTransaction(**transaction)
        elif service == 'manual_investments':
            transaction = ManualInvestmentTransaction(**transaction)
        else:
            raise ValueError("Currently, only 'cash' and 'manual_investments' services are supported for manually adding transactions.")

        return self.transactions_repository.add_transaction(transaction, service)

    def get_table_columns_for_display(self) -> List[str]:
        """
        Get the columns of the transactions table.

        Returns
        -------
        List[str]
            A list of column names in the transactions table.
        """
        cols = [
            self.transactions_repository.provider_col,
            self.transactions_repository.account_name_col,
            self.transactions_repository.account_number_col,
            self.transactions_repository.date_col,
            self.transactions_repository.desc_col,
            self.transactions_repository.amount_col,
            self.transactions_repository.category_col,
            self.transactions_repository.tag_col,
            self.transactions_repository.id_col,
            self.transactions_repository.status_col,
            self.transactions_repository.type_col
        ]
        return cols

    def get_data_for_analysis(self) -> pd.DataFrame:
        """
        Get table data for analysis purposes.

        Returns
        -------
        pd.DataFrame
            The table data formatted for analysis.
        """
        # Convert display name back to internal format
        cc_data = self.get_table_for_analysis('credit_card')
        bank_data = self.get_table_for_analysis('bank')
        cash_data = self.get_table_for_analysis('cash')
        manual_investments_data = self.get_table_for_analysis('manual_investments')
        return pd.concat([cc_data, bank_data, cash_data, manual_investments_data], ignore_index=True)

    def update_tagging_by_id(self, id_: str, category: str | None, tag: str | None) -> None:
        """
        Update the category and tag for a transaction by ID.

        Parameters
        ----------
        id_ : str
            The ID of the transaction to update.
        category : str
            The new category for the transaction.
        tag : str
            The new tag for the transaction.

        Returns
        -------
        None
        """
        self.transactions_repository.cc_repo.update_tagging_by_id(id_, category, tag)
        self.transactions_repository.bank_repo.update_tagging_by_id(id_, category, tag)
        self.transactions_repository.cash_repo.update_tagging_by_id(id_, category, tag)

    def update_transaction_by_id(self, transaction_id: str, updates: dict) -> bool:
        """
        Update a transaction by ID with the given field updates.

        Parameters
        ----------
        transaction_id : str
            The ID of the transaction to update.
        updates : dict
            Dictionary of field names and their new values.

        Returns
        -------
        bool
            True if the update was successful, False otherwise.
        """
        cc_res = self.transactions_repository.cc_repo.update_transaction_by_id(transaction_id, updates)
        bank_res = self.transactions_repository.bank_repo.update_transaction_by_id(transaction_id, updates)
        cash_res = self.transactions_repository.cash_repo.update_transaction_by_id(transaction_id, updates)
        return cc_res or bank_res or cash_res

    def delete_transaction_by_id(self, transaction_id: str) -> bool:
        """
        Delete a transaction by ID. supports cash transactions only.

        Parameters
        ----------
        transaction_id : str
            The ID of the transaction to delete.

        Returns
        -------
        bool
            True if the deletion was successful, False otherwise.
        """
        cash_res = self.transactions_repository.cash_repo.delete_transaction_by_id(transaction_id)
        return cash_res

    def get_transactions_by_tag(
        self,
        category: str,
        tag: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get all transactions related to a specific investment.

        Parameters
        ----------
        category : str
            Category to filter scraped transactions
        tag : str, optional
            Tag to filter scraped transactions

        Returns
        -------
        pd.DataFrame
            DataFrame containing all relevant investment transactions.
        """
        df = self.get_data_for_analysis()
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        investment_df = df[df[category_col] == category]
        if tag:
            investment_df = investment_df[investment_df[tag_col] == tag]
        return investment_df.reset_index(drop=True)

    def get_all_transactions(self, service: Literal['credit_card', 'bank', 'cash']) -> pd.DataFrame:
        """
        Get all transactions for the specified service.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            The service for which to get transactions.

        Returns
        -------
        pd.DataFrame
            All transactions for the specified service.
        """
        if service not in ['credit_card', 'bank', 'cash']:
            raise ValueError(f"service must be either 'credit_card' or 'bank'. Got '{service}'")

        return self.transactions_repository.get_table(service)

    def get_untagged_transactions(self, service: Literal['credit_card', 'bank'], account_number: Optional[str] = None) -> pd.DataFrame:
        """
        Get transactions that don't have categories assigned.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            Service to get transactions from.
        account_number : Optional[str]
            Account number filter for bank transactions.

        Returns
        -------
        pd.DataFrame
            Untagged transactions.
        """
        transactions = self.transactions_repository.get_table(service)
        category_col = TransactionsTableFields.CATEGORY.value

        # Filter for untagged transactions
        untagged = transactions[transactions[category_col].isna()]

        if account_number and service == 'bank':
            account_col = TransactionsTableFields.ACCOUNT_NUMBER.value
            untagged = untagged[untagged[account_col] == account_number]

        return untagged

    def get_latest_data_date(self) -> datetime:
        """
        Get the latest date of transactions across all tables.
        Business logic for calculating the minimum date across multiple tables.

        Returns
        -------
        datetime
            The latest date of transactions across all tables.
        """
        latest_dates = []
        tables = self.transactions_repository.get_all_table_names()

        for table in tables:
            latest_date = self.transactions_repository.get_latest_date_from_table(table)
            if latest_date is not None:
                latest_dates.append(latest_date)
            else:
                # Default to one year ago if no data exists
                latest_dates.append(datetime.today() - timedelta(days=365))

        # Return the minimum date (earliest of the latest dates)
        return min(latest_dates) if latest_dates else datetime.today() - timedelta(days=365)

    def get_table_for_analysis(self, service: Literal['credit_card', 'bank', 'cash', 'manual_investments'] = 'credit_card') -> pd.DataFrame:
        """
        Returns the transactions table for the specified service, replacing rows with split transactions by their splits.

        This method contains the business logic that was moved from TransactionsRepository.
        It coordinates between TransactionsRepository and SplitTransactionsRepository to merge data.

        The returned DataFrame has the same columns as the original, with split rows replacing the originals,
        and all other rows unchanged.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            The service for which to return the table ('credit_card' or 'bank').

        Returns
        -------
        pd.DataFrame
            The transactions table with split transactions expanded.
        """
        # Get base transaction data
        df = self.transactions_repository.get_table(service).copy()

        # Define analysis columns
        analysis_cols = [
            self.transactions_repository.id_col,
            self.transactions_repository.date_col,
            self.transactions_repository.provider_col,
            self.transactions_repository.account_name_col,
            self.transactions_repository.account_number_col,
            self.transactions_repository.desc_col,
            self.transactions_repository.amount_col,
            self.transactions_repository.category_col,
            self.transactions_repository.tag_col
        ]

        # Get all splits for this service
        split_df = self.split_transactions_repository.get_data()
        if split_df.empty:
            return df[analysis_cols]

        # Prepare for merging: drop original transactions that have splits, and add split rows
        split_df = split_df[split_df['transaction_id'].isin(df[self.transactions_repository.id_col])]  # filter out unneeded splits
        split_ids = set(split_df['transaction_id'])
        mask = df[self.transactions_repository.id_col].isin(split_ids)
        base_df = df[~mask].copy()

        # For each split, get the original transaction row, update amount/category/tag, and append
        split_rows = []
        for id_, split_group in split_df.groupby(self.split_transactions_repository.transaction_id_col):
            orig_row = df[df[self.transactions_repository.id_col] == id_]
            if orig_row.empty:
                continue
            for _, split in split_group.iterrows():
                split_row = orig_row.copy()
                split_row[self.transactions_repository.amount_col] = split[
                    self.split_transactions_repository.amount_col]
                split_row[self.transactions_repository.category_col] = split[
                    self.split_transactions_repository.category_col]
                split_row[self.transactions_repository.tag_col] = split[self.split_transactions_repository.tag_col]
                split_rows.append(split_row)

        if split_rows:
            split_rows_df = pd.concat(split_rows, ignore_index=True)
            result_df = pd.concat([base_df, split_rows_df], ignore_index=True)
        else:
            result_df = base_df

        return result_df[analysis_cols].reset_index(drop=True)

    def get_kpis(self, df: pd.DataFrame) -> dict:
        """
        Calculate KPIs for the given DataFrame (should be filtered by user selection).
        """
        data = self.split_data_by_category_types(df)
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value
        period_income = data['income'][amount_col].sum()
        period_expenses = data['expenses'][amount_col].sum() * -1 + 0  # add 0 to avoid -0 printing later on
        period_savings = data['savings'][amount_col].sum() * -1 + 0
        period_liabilities_paid = data['liabilities'][data['liabilities'][amount_col] < 0][amount_col].sum() * -1 + 0
        period_liabilities_received = data['liabilities'][data['liabilities'][amount_col] > 0][amount_col].sum()
        bank_balance_increase = period_income - period_expenses - period_liabilities_paid - period_savings
        total_savings = bank_balance_increase + period_savings
        actual_savings_rate = (total_savings / period_income * 100) if period_income != 0 else 0
        largest_expense_cat = (
            data['expenses'].groupby(category_col)[amount_col].sum().abs().sort_values(ascending=False)
        )
        largest_expense_cat_name = largest_expense_cat.index[0] if not largest_expense_cat.empty else "-"
        largest_expense_cat_val = largest_expense_cat.iloc[0] if not largest_expense_cat.empty else 0
        return {
            'income': period_income,
            'expenses': period_expenses,
            'savings_and_investments': period_savings,
            'bank_balance_increase': bank_balance_increase,
            'savings_rate': actual_savings_rate,
            'liabilities_paid': period_liabilities_paid,
            'liabilities_received': period_liabilities_received,
            'largest_expense_cat_name': largest_expense_cat_name,
            'largest_expense_cat_val': largest_expense_cat_val
        }

    @staticmethod
    def split_data_by_category_types(df: pd.DataFrame) -> dict:
        """
        Split the given DataFrame into expenses, savings, income, and liabilities DataFrames.
        Savings amounts are flipped to positive.
        """
        category_col = TransactionsTableFields.CATEGORY.value
        savings_categories = [e.value for e in SavingsAndInvestmentsCategories]
        income_categories = [e.value for e in IncomeCategories]
        liabilities_categories = [e.value for e in LiabilitiesCategories]
        non_expenses_categories = [e.value for e in NonExpensesCategories]
        expenses_data = df[~df[category_col].isin(non_expenses_categories)]
        savings_data = df[df[category_col].isin(savings_categories)].copy()
        income_data = df[df[category_col].isin(income_categories)]
        liabilities_data = df[df[category_col].isin(liabilities_categories)]
        return {
            'expenses': expenses_data,
            'savings': savings_data,
            'income': income_data,
            'liabilities': liabilities_data
        }

    def get_liabilities_summary(self, filtered_df: pd.DataFrame) -> dict:
        """
        Get liabilities summary: total received, total paid, net change (all positive), and per-tag summary (filtered).
        Uses all data for total received/paid, but filtered data for per-tag/monthly breakdown.
        """
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value
        liabilities_categories = [e.value for e in LiabilitiesCategories]
        all_data = self.get_data_for_analysis()
        all_liabilities = all_data[all_data[category_col].isin(liabilities_categories)]
        filtered_liabilities = filtered_df[filtered_df[category_col].isin(liabilities_categories)]
        total_received = all_liabilities[all_liabilities[amount_col] > 0][amount_col].sum()
        total_paid = abs(all_liabilities[all_liabilities[amount_col] < 0][amount_col].sum())
        net_change = total_received - total_paid
        # Per-tag breakdown (filtered)
        tag_summary = filtered_liabilities.groupby(tag_col)[amount_col].agg([
            lambda x: abs(x[x > 0].sum()),  # Received
            lambda x: abs(x[x < 0].sum()),  # Paid
            lambda x: abs(x.sum())  # Net (always positive)
        ]).reset_index()
        tag_summary.columns = ['Name', 'Received', 'Paid', 'Outstanding Balance']
        return {
            'total_received': abs(total_received),
            'total_paid': abs(total_paid),
            'outstanding_balance': abs(net_change),
            'tag_summary': tag_summary,
            'filtered_liabilities': filtered_liabilities
        }

    @staticmethod
    def get_providers_for_service(service: Literal['credit_card', 'bank']) -> List[str]:
        """
        Get a list of providers for the specified service.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            The service to get providers for.

        Returns
        -------
        List[str]
            A list of provider names for the specified service.

        Raises
        ------
        ValueError
            If the service is not recognized.
        """
        if service == Services.CREDIT_CARD.value:
            return [e.value for e in CreditCards]
        elif service == Services.BANK.value:
            return [e.value for e in Banks]
        else:
            raise ValueError(f"Service must be either 'credit_card' or 'bank'. Got '{service}'")

    @staticmethod
    def get_all_providers() -> List[str]:
        """
        Get a list of all providers across both credit card and bank services.

        Returns
        -------
        List[str]
            A list of all provider names.
        """
        cc_providers = [e.value for e in CreditCards]
        bank_providers = [e.value for e in Banks]
        return cc_providers + bank_providers