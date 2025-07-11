from typing import List, Literal, Dict, Any

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.split_transactions_repository import SplitTransactionsRepository
from fad.app.data_access.transactions_repository import TransactionsRepository


class SplitTransactionsService:
    """
    Service for managing split transactions.

    This class provides methods for splitting transactions into multiple parts,
    each with its own amount, category, and tag.

    Attributes
    ----------
    split_transactions_repository : SplitTransactionsRepository
        Repository for managing split transactions data.
    transactions_repository : TransactionsRepository
        Repository for managing transaction data.
    """

    def __init__(self, conn: SQLConnection = get_db_connection()):
        """
        Initialize the SplitTransactionsService.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.split_transactions_repository = SplitTransactionsRepository(conn)
        self.transactions_repository = TransactionsRepository(conn)

    def get_transaction_by_id(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> pd.Series:
        """
        Get a transaction by its ID.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        pd.Series
            The transaction data.
        """
        df = self.transactions_repository.get_table(service)
        transaction = df[df[self.transactions_repository.id_col] == transaction_id]
        if transaction.empty:
            raise ValueError(f"Transaction with ID {transaction_id} not found in {service} transactions.")
        return transaction.iloc[0]

    def get_splits_for_transaction(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """
        Get all splits for a specific transaction.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing all splits for the transaction.
        """
        return self.split_transactions_repository.get_splits_for_transaction(transaction_id, service)

    def split_transaction(self, transaction_id: int, service: Literal['credit_card', 'bank'], 
                         splits: List[Dict[str, Any]]) -> None:
        """
        Split a transaction into multiple parts.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction to split.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.
        splits : List[Dict[str, Any]]
            A list of dictionaries, each containing 'amount', 'category', and 'tag' for a split.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If the total amount of the splits does not equal the original transaction amount.
        """
        # Get the original transaction
        transaction = self.get_transaction_by_id(transaction_id, service)
        original_amount = transaction[self.transactions_repository.amount_col]

        # Calculate the total amount of the splits
        total_split_amount = sum(split['amount'] for split in splits)

        # Validate that the total amount of the splits equals the original transaction amount (with epsilon)
        if abs(total_split_amount - original_amount) > 1e-6:
            raise ValueError(
                f"Total split amount ({total_split_amount}) does not equal original transaction amount ({original_amount})."
            )

        # Delete any existing splits for this transaction
        self.split_transactions_repository.delete_all_splits_for_transaction(transaction_id, service)

        # Add the new splits
        for split in splits:
            self.split_transactions_repository.add_split(
                transaction_id=transaction_id,
                service=service,
                amount=split['amount'],
                category=split['category'],
                tag=split['tag']
            )

    def cancel_split(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> None:
        """
        Cancel a split transaction by deleting all splits for the transaction.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        self.split_transactions_repository.delete_all_splits_for_transaction(transaction_id, service)

    def has_splits(self, transaction_id: int, service: Literal['credit_card', 'bank']) -> bool:
        """
        Check if a transaction has any splits.

        Parameters
        ----------
        transaction_id : int
            The ID of the transaction.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        bool
            True if the transaction has splits, False otherwise.
        """
        splits = self.get_splits_for_transaction(transaction_id, service)
        return not splits.empty