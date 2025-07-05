from datetime import datetime, timedelta
from typing import List, Literal

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository


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

    def get_table_data_for_analysis(self, table_name: str) -> pd.DataFrame:
        """
        Get table data for analysis purposes.

        Parameters
        ----------
        table_name : str
            The name of the table to retrieve data from.

        Returns
        -------
        pd.DataFrame
            The table data formatted for analysis.
        """
        # Convert display name back to internal format
        service_name = table_name.lower().replace(' ', '_')
        if service_name == 'credit_card':
            return self.get_table_for_analysis('credit_card')
        elif service_name == 'bank':
            return self.get_table_for_analysis('bank')
        else:
            raise ValueError(f"Unknown table name: {table_name}")

    def update_tagging(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                       account_number: str | None = None) -> None:
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

    def update_tagging_by_id(self, id_: int, category: str, tag: str, service: Literal['credit_card', 'bank']) -> None:
        """
        Update the tags of the raw data in the credit card and bank tables by transaction ID.
        Business logic for routing tagging operations by ID.

        Parameters
        ----------
        id_ : int
            The ID of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        if service not in ['credit_card', 'bank']:
            raise ValueError(f"service must be either 'credit_card' or 'bank'. Got '{service}'")

        if service == 'credit_card':
            self.transactions_repository.cc_repo.update_tagging_by_id(id_, category, tag)
        else:
            self.transactions_repository.bank_repo.update_tagging_by_id(id_, category, tag)

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
        split_df = self.split_transactions_repository.get_data(service)
        if split_df.empty:
            return df[analysis_cols]

        # Prepare for merging: drop original transactions that have splits, and add split rows
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
                split_row[self.transactions_repository.amount_col] = split[self.split_transactions_repository.amount_col]
                split_row[self.transactions_repository.category_col] = split[self.split_transactions_repository.category_col]
                split_row[self.transactions_repository.tag_col] = split[self.split_transactions_repository.tag_col]
                split_rows.append(split_row)

        if split_rows:
            split_rows_df = pd.concat(split_rows, ignore_index=True)
            result_df = pd.concat([base_df, split_rows_df], ignore_index=True)
        else:
            result_df = base_df

        return result_df[analysis_cols].reset_index(drop=True)
