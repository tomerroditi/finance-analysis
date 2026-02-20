"""
Service for managing bank account balances and prior wealth calculations.
"""

from datetime import date

from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.errors import ValidationException
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions_repository import TransactionsRepository


class BankBalanceService:
    """Service for managing bank account balances and prior wealth calculations."""

    def __init__(self, db: Session):
        self.db = db
        self.balance_repo = BankBalanceRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.scraping_history_repo = ScrapingHistoryRepository(db)

    def get_all_balances(self) -> list[dict]:
        """
        Get all bank balance records.

        Returns
        -------
        list[dict]
            List of balance records with all fields.
        """
        df = self.balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(self, provider: str, account_name: str, balance: float) -> dict:
        """
        Set the current balance for a bank account.

        Calculates prior_wealth as: balance - sum(all scraped bank txns for this account).
        Validates that the last successful scrape for this account is today.

        Parameters
        ----------
        provider : str
            Bank provider name (e.g. "hapoalim").
        account_name : str
            User's display name for the account.
        balance : float
            The current balance entered by the user.

        Returns
        -------
        dict
            The created/updated balance record.

        Raises
        ------
        ValidationException
            If the last successful scrape is not today.
        """
        self._validate_scrape_is_today(provider, account_name)

        txn_sum = self._get_account_transaction_sum(provider, account_name)
        prior_wealth = balance - txn_sum

        record = self.balance_repo.upsert(
            provider=provider,
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=prior_wealth,
            last_manual_update=date.today().isoformat(),
        )

        return {
            "id": record.id,
            "provider": record.provider,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
            "last_scrape_update": record.last_scrape_update,
        }

    def recalculate_for_account(self, provider: str, account_name: str) -> None:
        """
        Recalculate balance after a scrape.

        balance = prior_wealth (fixed) + sum(all scraped bank txns).
        Only acts if a balance record exists for this account.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            User's display name for the account.
        """
        existing = self.balance_repo.get_by_account(provider, account_name)
        if not existing:
            return

        txn_sum = self._get_account_transaction_sum(provider, account_name)
        new_balance = existing.prior_wealth_amount + txn_sum

        self.balance_repo.upsert(
            provider=provider,
            account_name=account_name,
            balance=new_balance,
            prior_wealth_amount=existing.prior_wealth_amount,
            last_scrape_update=date.today().isoformat(),
        )

    def delete_for_account(self, provider: str, account_name: str) -> None:
        """
        Delete balance record when account is disconnected.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            User's display name for the account.
        """
        self.balance_repo.delete_by_account(provider, account_name)

    def _validate_scrape_is_today(self, provider: str, account_name: str) -> None:
        """Validate that last successful scrape for this account is today."""
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
            service_name="banks",
            provider_name=provider,
            account_name=account_name,
        )
        if not last_scrape:
            raise ValidationException(
                "No successful scrape found for this account. Scrape today first."
            )

        scrape_date = last_scrape[:10]  # Extract YYYY-MM-DD from ISO timestamp
        if scrape_date != date.today().isoformat():
            raise ValidationException(
                "Last scrape is not from today. Scrape today first to set balance."
            )

    def _get_account_transaction_sum(self, provider: str, account_name: str) -> float:
        """Get the sum of all bank transactions for a specific account."""
        df = self.transactions_repo.get_table(service=Services.BANK.value)
        if df.empty:
            return 0.0
        mask = (df["provider"] == provider) & (df["account_name"] == account_name)
        return float(df.loc[mask, "amount"].sum())

    def get_total_prior_wealth(self) -> float:
        """Get total prior wealth from all bank accounts."""
        df = self.balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())