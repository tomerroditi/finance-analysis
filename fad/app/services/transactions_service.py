from datetime import datetime, timedelta
from typing import List, Literal

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository
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

    def get_table_names_for_display(self) -> List[str]:
        """
        Get the names of the transactions tables.

        Returns
        -------
        List[str]
            A list of table names.
        """
        tables = self.transactions_repository.get_all_table_names()
        tables = [name.replace('_', ' ').title() for name in tables]
        return tables

    def get_table_data_for_display(self, table_name: str) -> pd.DataFrame:
        """
        Get table data for display purposes.

        Parameters
        ----------
        table_name : str
            The name of the table to retrieve data from.

        Returns
        -------
        pd.DataFrame
            The table data formatted for display.
        """
        # Convert display name back to internal format
        service_name = table_name.lower().replace(' ', '_')
        if service_name == 'credit_card':
            return self.transactions_repository.get_table('credit_card')
        elif service_name == 'bank':
            return self.transactions_repository.get_table('bank')
        else:
            raise ValueError(f"Unknown table name: {table_name}")

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
        return pd.concat([cc_data, bank_data])

    def update_tagging(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'], account_number: str | None = None) -> None:
        """
        Update the tags of the raw data in the credit card and bank tables.
        Business logic for routing tagging operations based on service type.

        Parameters
        ----------
        name : str
            The name of the transaction
        category : str
            The category to tag the transaction with
        tag : str
            The tag to tag the transaction with
        service : str
            The service of the transaction, should be one of 'credit_card' or 'bank'
        account_number : str | None
            The account number of the transaction, only used for bank transactions

        Returns
        -------
        None
        """
        if service not in ['credit_card', 'bank']:
            raise ValueError("service must be either 'credit_card' or 'bank'")

        if service == 'credit_card':
            self.transactions_repository.cc_repo.update_tagging_by_name(name, category, tag)
        else:
            if account_number is None:
                raise ValueError("account_number should be provided for bank transactions tagging")
            self.transactions_repository.bank_repo.update_tagging_by_name_and_account_number(
                name, account_number, category, tag
            )

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
        return cc_res or bank_res

    def get_all_transactions(self, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
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
        if service not in ['credit_card', 'bank']:
            raise ValueError(f"service must be either 'credit_card' or 'bank'. Got '{service}'")

        return self.transactions_repository.get_table(service)

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

    def get_table_for_analysis(self, service: Literal['credit_card', 'bank'] = 'credit_card') -> pd.DataFrame:
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

    def split_data_by_category_types(self, df: pd.DataFrame) -> dict:
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

    def get_data_by_description(self, description: str, service: Literal['credit_card', 'bank'], account_number: str = None) -> pd.DataFrame:
        """
        Get transactions by description for a specific service.

        Parameters
        ----------
        description : str
            The description to filter transactions by.
        service : Literal['credit_card', 'bank']
            The service to filter transactions from.
        account_number : str, optional
            The account number to filter transactions by (only for bank service).

        Returns
        -------
        pd.DataFrame
            DataFrame containing transactions matching the description.
        """
        return self.transactions_repository.get_data_by_description(description, service, account_number)

    def get_service_from_provider(self, provider: str) -> str:
        """
        Get the service type ('credit_card' or 'bank') based on the provider name.

        Parameters
        ----------
        provider : str
            The provider name to look up.

        Returns
        -------
        str
            The service type corresponding to the provider. either 'credit_card' or 'bank'.

        Raises
        ------
        ValueError
            If the provider is not found in either service.
        """
        if provider in [e.value for e in CreditCards]:
            return Services.CREDIT_CARD.value
        elif provider in [e.value for e in Banks]:
            return Services.BANK.value
        else:
            raise ValueError(f"Provider '{provider}' not found in either credit card or bank services.")