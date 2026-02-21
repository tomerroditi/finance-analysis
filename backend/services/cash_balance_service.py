"""Service for managing cash account balances and prior wealth.

This module orchestrates cash balance operations including balance updates,
prior wealth calculations, and balance recalculation based on transactions.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.repositories.cash_balance_repository import CashBalanceRepository
from backend.repositories.transactions_repository import CashRepository
from backend.models.transaction import CashTransaction


class CashBalanceService:
    """
    Service for managing cash account balances and prior wealth snapshots.

    Handles balance updates, prior wealth calculations, and recalculation
    of balances based on cash transactions.
    """

    def __init__(self, db: Session):
        """
        Initialize the cash balance service.

        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db
        self.cash_balance_repo = CashBalanceRepository(db)
        self.cash_repo = CashRepository(db)

    def get_all_balances(self) -> list[dict]:
        """
        Get all cash account balances.

        Returns
        -------
        list[dict]
            List of balance records as dicts with keys: account_name, balance,
            prior_wealth_amount, last_manual_update, id.
        """
        df = self.cash_balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(self, account_name: str, balance: float) -> dict:
        """
        Set the balance for a cash account and calculate prior wealth.

        Prior wealth is calculated as: balance - sum(all cash transactions for account).

        Parameters
        ----------
        account_name : str
            Cash account name.
        balance : float
            Current balance to set.

        Returns
        -------
        dict
            Updated balance record as a dict.

        Raises
        ------
        ValueError
            If balance is negative.
        """
        if balance < 0:
            raise ValueError("Balance must be >= 0")

        # Calculate sum of transactions for this account
        txn_sum = self._get_account_transaction_sum(account_name)

        # prior_wealth = balance - sum(transactions)
        prior_wealth = balance - txn_sum

        # Upsert the balance record
        record = self.cash_balance_repo.upsert(
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=prior_wealth,
        )

        return self._record_to_dict(record)

    def recalculate_current_balance(self, account_name: str) -> dict:
        """
        Recalculate the current balance for a cash account, keeping prior wealth fixed.

        New balance = prior_wealth + sum(cash transactions for account).

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        dict
            Updated balance record as a dict.
        """
        # Get existing record to preserve prior_wealth
        existing = self.cash_balance_repo.get_by_account_name(account_name)
        if not existing:
            # If no record exists, create one with balance = transaction sum
            txn_sum = self._get_account_transaction_sum(account_name)
            record = self.cash_balance_repo.upsert(
                account_name=account_name,
                balance=txn_sum,
                prior_wealth_amount=0.0,
            )
            return self._record_to_dict(record)

        # Preserve existing prior_wealth
        prior_wealth = existing.prior_wealth_amount

        # Recalculate balance as prior_wealth + sum(transactions)
        txn_sum = self._get_account_transaction_sum(account_name)
        new_balance = prior_wealth + txn_sum

        # Update with new balance, keep prior_wealth the same
        record = self.cash_balance_repo.upsert(
            account_name=account_name,
            balance=new_balance,
            prior_wealth_amount=prior_wealth,
        )

        return self._record_to_dict(record)

    def get_by_account_name(self, account_name: str) -> Optional[dict]:
        """
        Get balance record for a specific cash account.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        dict or None
            Balance record as a dict, or None if not found.
        """
        record = self.cash_balance_repo.get_by_account_name(account_name)
        if record is None:
            return None
        return self._record_to_dict(record)

    def get_total_prior_wealth(self) -> float:
        """
        Get the sum of all prior wealth amounts across all cash accounts.

        Returns
        -------
        float
            Sum of prior_wealth_amount across all cash accounts.
        """
        df = self.cash_balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def delete_for_account(self, account_name: str) -> None:
        """
        Delete the balance record for a cash account.

        Parameters
        ----------
        account_name : str
            Cash account name.
        """
        self.cash_balance_repo.delete_by_account_name(account_name)

    def _get_account_transaction_sum(self, account_name: str) -> float:
        """
        Calculate the sum of all cash transactions for an account.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        float
            Sum of all cash transaction amounts for the account.
        """
        # Get cash transactions for this account
        stmt = select(CashTransaction).where(
            CashTransaction.account_name == account_name
        )
        transactions_df = self.cash_repo.get_table()

        if transactions_df.empty:
            return 0.0

        # Filter to just this account
        account_df = transactions_df[transactions_df["account_name"] == account_name]
        if account_df.empty:
            return 0.0

        return float(account_df["amount"].sum())

    @staticmethod
    def _record_to_dict(record) -> dict:
        """
        Convert a CashBalance ORM record to a dict.

        Parameters
        ----------
        record : CashBalance
            ORM model instance.

        Returns
        -------
        dict
            Dict with keys: id, account_name, balance, prior_wealth_amount, last_manual_update.
        """
        return {
            "id": record.id,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
        }
