from typing import List
import pandas as pd
from streamlit.connections import SQLConnection
from typing import Literal
from fad.app.data_access.transactions_repository import TransactionsRepository


class TransactionsService:
    def __init__(self, conn: SQLConnection):
        self.transactions_repository = TransactionsRepository(conn)

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
        tables = self.transactions_repository.tables
        tables = [name.replace('_', ' ').title() for name in tables]
        return tables

    def get_table_data_for_display(self, table_name: str) -> pd.DataFrame:
        """
        Get the data from the specified transactions table.

        Parameters
        ----------
        table_name : str
            The name of the table to retrieve data from.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing the data from the specified table.
        """
        table_name: Literal["credit_card", "bank"] = table_name.lower().replace(' ', '_') # noqa
        table = self.transactions_repository.get_table(table_name)
        return table

    def update_data_table(self, service: Literal['credit_card', 'bank'], id_: int, category: str, tag: str) -> None:
        """
        update the tags of the raw data in the credit card and bank tables.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            the service of the transaction, should be one of 'credit_card' or 'bank'
        id_ : int
            the id of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with

        Returns
        -------
        None
        """
        assert service in ['credit_card', 'bank'], f"service must be either 'credit_card' or 'bank' got {service}"
        self.transactions_repository.update_tagging_by_id(id_, category, tag, service)
