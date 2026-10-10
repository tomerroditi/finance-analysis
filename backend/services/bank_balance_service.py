"""Service for managing bank account balances and prior wealth calculations.

An account's balance comes from one of two places. Most banks report it on
every scrape, and that figure wins: the account's prior wealth is re-derived
so that prior wealth plus every tracked transaction lands on what the bank
says (:meth:`BankBalanceService.apply_scraped_balance`). Banks that report
none — and anyone correcting a figure by hand — set it manually
(:meth:`BankBalanceService.set_balance`); between those entries a scrape only
re-adds the transactions to the prior wealth already stored.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.errors import ValidationException
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions import TransactionsRepository

SOURCE_SCRAPED = "scraped"
SOURCE_MANUAL = "manual"

#: Below this a drift between the bank and the app is rounding, not a gap.
DRIFT_TOLERANCE = 0.005


class BankBalanceService:
    """Service for managing bank account balances and prior wealth calculations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.balance_repo = BankBalanceRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.scraping_history_repo = ScrapingHistoryRepository(db)

    def get_all_balances(self) -> list[dict[str, Any]]:
        """Get all bank balance records.

        Returns
        -------
        list[dict[str, Any]]
            List of balance records with all fields.
        """
        df = self.balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(
        self, provider: str, account_name: str, balance: float
    ) -> dict[str, Any]:
        """Set the current balance for a bank account.

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
        dict[str, Any]
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
            balance_source=SOURCE_MANUAL,
            last_drift=0.0,
        )

        return {
            "id": record.id,
            "provider": record.provider,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
            "last_scrape_update": record.last_scrape_update,
            "balance_source": record.balance_source,
            "last_drift": record.last_drift,
        }

    def apply_scraped_balance(
        self, provider: str, account_name: str, balance: float
    ) -> float | None:
        """Take the balance a scrape reported as the account's balance.

        Prior wealth becomes ``balance - sum(all tracked transactions)``, so
        the account's computed balance equals the bank's from now on, and its
        history moves with it. Before that, the gap between the bank's figure
        and the one the app would have computed is kept as ``last_drift``:
        a non-zero drift means the tracked transactions do not add up to what
        the bank holds — one is missing, duplicated or wrong — which the
        correction itself would otherwise hide.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            User's display name for the account.
        balance : float
            The balance the bank reported, summed over the credential's
            checking accounts.

        Returns
        -------
        float or None
            The drift (bank less computed), or None for an account that had
            no balance to compare with yet.
        """
        txn_sum = self._get_account_transaction_sum(provider, account_name)
        existing = self.balance_repo.get_by_account(provider, account_name)
        drift = None
        if existing is not None:
            drift = balance - (existing.prior_wealth_amount + txn_sum)
            if abs(drift) < DRIFT_TOLERANCE:
                drift = 0.0
        self.balance_repo.upsert(
            provider=provider,
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=balance - txn_sum,
            last_scrape_update=date.today().isoformat(),
            balance_source=SOURCE_SCRAPED,
            last_drift=round(drift, 2) if drift is not None else 0.0,
        )
        return drift

    def recalculate_for_account(self, provider: str, account_name: str) -> None:
        """Recalculate balance after a scrape that reported no balance.

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
        """Delete balance record when account is disconnected.

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
            service_name=Services.BANK.value,
            provider_name=provider,
            account_name=account_name,
        )
        if not last_scrape:
            raise ValidationException(
                "No successful scrape found for this account. Scrape today first."
            )

        scrape_date = last_scrape[:10]
        if scrape_date != date.today().isoformat():
            raise ValidationException(
                "Last scrape is not from today. Scrape today first to set balance."
            )

    def _get_account_transaction_sum(self, provider: str, account_name: str) -> float:
        """Get the sum of all bank transactions for a specific account.

        Counted as the merged transactions view shows the account: split
        parents are replaced by their slices.
        """
        if provider is None:
            return 0.0
        return self.transactions_repo.bank_repo.sum_amount(
            account_name, provider, expand_splits=True
        )

    def get_total_prior_wealth(self) -> float:
        """Get total prior wealth from all bank accounts."""
        df = self.balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())
