"""Service for managing cash account balances and prior wealth.

This module orchestrates cash balance operations including balance updates,
prior wealth calculations, and balance recalculation based on transactions.
"""

from typing import Any

import pandas as pd
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.models.cash_balance import CashBalance
from backend.models.transaction import CashTransaction
from backend.repositories.cash_balance_repository import CashBalanceRepository
from backend.repositories.transactions import CashRepository


class CashBalanceService:
    """Service for managing cash account balances and prior wealth snapshots.

    Handles balance updates, prior wealth calculations, and recalculation
    of balances based on cash transactions.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cash_balance_repo = CashBalanceRepository(db)
        self.cash_repo = CashRepository(db)

    def get_all_balances(self) -> list[dict[str, Any]]:
        """Get all cash account balances.

        Returns
        -------
        list[dict[str, Any]]
            List of balance records as dicts with keys: account_name, balance,
            prior_wealth_amount, last_manual_update, id.
        """
        df = self.cash_balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(self, account_name: str, balance: float) -> dict[str, Any]:
        """Set the balance for a cash account and calculate prior wealth.

        Prior wealth is calculated as: balance - sum(all cash transactions for account).

        Parameters
        ----------
        account_name : str
            Cash account name.
        balance : float
            Current balance to set.

        Returns
        -------
        dict[str, Any]
            Updated balance record as a dict.

        Raises
        ------
        ValueError
            If balance is negative.
        """
        if balance < 0:
            raise ValueError("Balance must be >= 0")

        txn_sum = self._get_account_transaction_sum(account_name)
        prior_wealth = balance - txn_sum

        record = self.cash_balance_repo.upsert(
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=prior_wealth,
        )

        return self._record_to_dict(record)

    def recalculate_current_balance(self, account_name: str) -> dict[str, Any]:
        """Recalculate the current balance for a cash account, keeping prior wealth fixed.

        New balance = prior_wealth + sum(cash transactions for account). An
        account with no balance record gets one with zero prior wealth.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        dict[str, Any]
            Updated balance record as a dict.
        """
        existing = self.cash_balance_repo.get_by_account_name(account_name)
        if not existing:
            txn_sum = self._get_account_transaction_sum(account_name)
            record = self.cash_balance_repo.upsert(
                account_name=account_name,
                balance=txn_sum,
                prior_wealth_amount=0.0,
            )
            return self._record_to_dict(record)

        prior_wealth = existing.prior_wealth_amount
        txn_sum = self._get_account_transaction_sum(account_name)
        new_balance = prior_wealth + txn_sum

        record = self.cash_balance_repo.upsert(
            account_name=account_name,
            balance=new_balance,
            prior_wealth_amount=prior_wealth,
        )

        return self._record_to_dict(record)

    def get_by_account_name(self, account_name: str) -> dict[str, Any] | None:
        """Get balance record for a specific cash account.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        dict[str, Any] or None
            Balance record as a dict, or None if not found.
        """
        record = self.cash_balance_repo.get_by_account_name(account_name)
        if record is None:
            return None
        return self._record_to_dict(record)

    def get_total_prior_wealth(self) -> float:
        """Get the sum of all prior wealth amounts across all cash accounts.

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
        """Delete the cash balance record for a cash account.

        Prevents deletion of the default "Wallet" account. Both the account's
        transactions **and** its prior wealth are folded into "Wallet" before
        deletion, so the envelope's money is preserved rather than dropped
        from net worth, the Sankey "Prior Wealth" node and the overview.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Raises
        ------
        ValueError
            If attempting to delete the "Wallet" account.
        """
        if account_name == "Wallet":
            raise ValueError("Cannot delete the default 'Wallet' account")

        # Carry the envelope's prior wealth over to Wallet. Deleting the row
        # without this silently destroys money that predates tracked
        # transactions — the migrated transactions alone don't represent it.
        deleted = self.cash_balance_repo.get_by_account_name(account_name)
        carried_prior_wealth = (
            float(deleted.prior_wealth_amount or 0.0) if deleted else 0.0
        )

        self._migrate_transactions_to_wallet(account_name)
        self.cash_balance_repo.delete_by_account_name(account_name)

        if carried_prior_wealth:
            wallet = self.cash_balance_repo.get_by_account_name("Wallet")
            wallet_prior_wealth = (
                float(wallet.prior_wealth_amount or 0.0) if wallet else 0.0
            ) + carried_prior_wealth
            self.cash_balance_repo.upsert(
                account_name="Wallet",
                balance=wallet_prior_wealth
                + self._get_account_transaction_sum("Wallet"),
                prior_wealth_amount=wallet_prior_wealth,
            )

    def _get_account_transaction_sum(self, account_name: str) -> float:
        """Calculate the sum of all cash transactions for an account.

        Parameters
        ----------
        account_name : str
            Cash account name.

        Returns
        -------
        float
            Sum of all cash transaction amounts for the account.
        """
        transactions_df = self.cash_repo.get_table()
        if transactions_df.empty:
            return 0.0

        account_df = transactions_df[transactions_df["account_name"] == account_name]
        if account_df.empty:
            return 0.0

        return float(account_df["amount"].sum())

    def migrate_from_transactions(self) -> list[dict[str, Any]]:
        """Seed cash_balances from existing cash transaction history.

        For each unique account_name in cash_transactions (excluding "Prior Wealth"):
          txn_sum = sum(all transactions for account)
          prior_wealth = max(0.0, -txn_sum)
          balance = prior_wealth + txn_sum

        Skips accounts that already have a cash_balances record.
        Deletes the old synthetic "Prior Wealth" row from cash_transactions.

        Returns
        -------
        list[dict[str, Any]]
            List of migrated account dicts with keys: id, account_name, balance,
            prior_wealth_amount, last_manual_update.
        """
        cash_df = self.cash_repo.get_table()
        migrated: list[dict[str, Any]] = []

        if not cash_df.empty:
            user_txns = cash_df[cash_df["account_name"] != "Prior Wealth"]

            for account_name, group in user_txns.groupby("account_name"):
                if self.cash_balance_repo.get_by_account_name(account_name):
                    continue

                txn_sum = float(
                    pd.to_numeric(group["amount"], errors="coerce").fillna(0).sum()
                )
                prior_wealth = max(0.0, -txn_sum)
                balance = prior_wealth + txn_sum

                record = self.cash_balance_repo.upsert(
                    account_name=account_name,
                    balance=balance,
                    prior_wealth_amount=prior_wealth,
                )
                migrated.append(self._record_to_dict(record))

        self._delete_prior_wealth_transaction()
        return migrated

    def _delete_prior_wealth_transaction(self) -> None:
        """Delete the synthetic Prior Wealth offset row from cash_transactions."""
        self.db.execute(
            delete(CashTransaction).where(
                (CashTransaction.tag == "Prior Wealth")
                & (CashTransaction.account_name == "Prior Wealth")
            )
        )
        self.db.commit()

    def _migrate_transactions_to_wallet(self, account_name: str) -> None:
        """Migrate all transactions from a deleted account to "Wallet".

        Updates the account_name field for all transactions from the source
        account to "Wallet", then recalculates balances for both accounts.

        Parameters
        ----------
        account_name : str
            Source account name to migrate from.
        """
        stmt = (
            update(CashTransaction)
            .where(CashTransaction.account_name == account_name)
            .values(account_name="Wallet")
        )
        self.db.execute(stmt)
        self.db.commit()

        self.recalculate_current_balance(account_name)
        self.recalculate_current_balance("Wallet")

    @staticmethod
    def _record_to_dict(record: CashBalance) -> dict[str, Any]:
        """Serialize a CashBalance ORM record to a plain dict."""
        return {
            "id": record.id,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
        }
