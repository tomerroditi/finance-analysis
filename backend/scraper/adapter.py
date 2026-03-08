"""Adapter bridging the new async Python scraper framework to the backend pipeline.

Translates ``ScrapingResult`` objects from the ``scraper`` package into
pandas DataFrames compatible with the existing transaction storage,
auto-tagging, and bank-balance-recalculation pipeline.

Note: imports from the root ``scraper`` package use ``_import_scraper_module``
to avoid the naming collision with ``backend.scraper``.
"""

import asyncio
import datetime
import importlib
import logging
import os
import sys
from datetime import date

import pandas as pd

from backend.config import AppConfig
from backend.constants.tables import Tables, TransactionsTableFields
from backend.database import get_db_context
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.bank_balance_service import BankBalanceService
from backend.services.tagging_rules_service import TaggingRulesService
from backend.services.tagging_service import CategoriesTagsService

logger = logging.getLogger(__name__)


def _import_scraper_module(name: str):
    """Import a module from the root ``scraper`` package.

    Ensures the project root is on ``sys.path`` so that the root-level
    ``scraper`` package is found instead of ``backend.scraper``.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return importlib.import_module(name)

# Maps frontend service names to DB table / source column values.
_SERVICE_TO_TABLE = {
    "credit_cards": Tables.CREDIT_CARD.value,
    "banks": Tables.BANK.value,
    "insurances": Tables.INSURANCE.value,
}


def create_adapter(
    service_name: str,
    provider_name: str,
    account_name: str,
    credentials: dict,
    start_date: date,
    process_id: int,
) -> "ScraperAdapter":
    """Create the appropriate adapter for the given service type.

    Parameters
    ----------
    service_name : str
        Service type (``"banks"``, ``"credit_cards"``, ``"insurances"``).
    provider_name, account_name, credentials, start_date, process_id
        Forwarded to the adapter constructor.

    Returns
    -------
    ScraperAdapter
        An ``InsuranceScraperAdapter`` for insurances, otherwise a base ``ScraperAdapter``.
    """
    cls = InsuranceScraperAdapter if service_name == "insurances" else ScraperAdapter
    return cls(service_name, provider_name, account_name, credentials, start_date, process_id)


class ScraperAdapter:
    """Bridges the scraper framework to the backend services pipeline.

    Runs an async scraper from the ``scraper`` package, converts the
    resulting ``ScrapingResult`` into a DataFrame, and feeds it through the
    same save / tag / rebalance pipeline used by the legacy Node.js scrapers.

    Parameters
    ----------
    service_name : str
        Service type (``"credit_cards"`` or ``"banks"``).
    provider_name : str
        Provider identifier (e.g. ``"isracard"``, ``"hapoalim"``).
    account_name : str
        User-assigned account label.
    credentials : dict
        Provider login fields (keys vary per provider).
    start_date : date
        Oldest transaction date to fetch.
    process_id : int
        Scraping history record ID for status tracking.
    """

    CANCEL = "cancel"

    def __init__(
        self,
        service_name: str,
        provider_name: str,
        account_name: str,
        credentials: dict,
        start_date: date,
        process_id: int,
    ):
        self.service_name = service_name
        self.provider_name = provider_name
        self.account_name = account_name
        self.credentials = credentials
        self.start_date = start_date
        self.process_id = process_id

        # 2FA state
        self._otp_code: str | None = None
        self._otp_event = asyncio.Event()

        # Pipeline state
        self._data: pd.DataFrame | None = None
        self._error: str = ""
        self._table_name: str = _SERVICE_TO_TABLE.get(service_name, "")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the scraper and feed results through the backend pipeline.

        Imports and instantiates the appropriate scraper, converts the
        ``ScrapingResult`` to a DataFrame, saves transactions, applies
        auto-tagging, and recalculates bank balances. Always records the
        outcome in the scraping history table.
        """
        _scraper_pkg = _import_scraper_module("scraper")
        create_scraper = _scraper_pkg.create_scraper
        scraper_is_2fa_required = _scraper_pkg.is_2fa_required
        ScraperOptions = _import_scraper_module("scraper.base.base_scraper").ScraperOptions

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] %s: %s: Scraping started (from %s)",
            ts, self.provider_name, self.account_name, self.start_date,
        )

        try:
            scraper = self._create_scraper(create_scraper, ScraperOptions)
            if scraper_is_2fa_required(self.provider_name):
                scraper.on_otp_request = self._otp_callback

            result = await scraper.scrape()

            if result.success:
                self._data = self._result_to_dataframe(result, self.service_name)
                if self._data is not None and not self._data.empty:
                    self._data = self._data.sort_values(by=["date"])
                    self._save_scraped_transactions()
                    self._apply_auto_tagging()
                    self._recalculate_bank_balances()
                    self._post_save_hook(result)
            else:
                self._error = result.error_message or result.error_type or "Unknown error"
                logger.error(
                    "%s: %s: Scraping failed — %s",
                    self.provider_name, self.account_name, self._error,
                )
        except Exception as exc:
            self._error = str(exc)
            logger.error(
                "%s: %s: Unexpected error — %s",
                self.provider_name, self.account_name, self._error,
            )
        finally:
            self._record_scraping_attempt(self.process_id)

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] %s: %s: Scraping finished",
            ts, self.provider_name, self.account_name,
        )

    def set_otp_code(self, code: str) -> None:
        """Set OTP code and signal the waiting coroutine.

        Parameters
        ----------
        code : str
            The one-time password, or ``"cancel"`` to abort the scrape.
        """
        self._otp_code = code
        self._otp_event.set()

    # ------------------------------------------------------------------
    # Scraper creation
    # ------------------------------------------------------------------

    def _create_scraper(self, create_scraper_fn, options_cls):
        """Instantiate the appropriate scraper, redirecting to dummies in demo mode.

        Parameters
        ----------
        create_scraper_fn : callable
            The ``scraper.create_scraper`` factory function.
        options_cls : type
            The ``ScraperOptions`` dataclass from the scraper package.

        Returns
        -------
        BaseScraper
            A configured scraper instance.
        """
        options = options_cls(
            start_date=self.start_date,
            show_browser=False,
        )

        if AppConfig().is_demo_mode and "test_" not in self.provider_name:
            _dummy_mod = _import_scraper_module("scraper.providers.test.dummy_regular")
            DummyCreditCardScraper = _dummy_mod.DummyCreditCardScraper
            DummyRegularScraper = _dummy_mod.DummyRegularScraper

            if self.service_name == "credit_cards":
                return DummyCreditCardScraper(self.provider_name, self.credentials, options)
            return DummyRegularScraper(self.provider_name, self.credentials, options)

        return create_scraper_fn(self.provider_name, self.credentials, options)

    # ------------------------------------------------------------------
    # 2FA callback
    # ------------------------------------------------------------------

    async def _otp_callback(self) -> str:
        """Async callback passed to the scraper for OTP requests.

        Clears the event, waits for ``set_otp_code`` to fire, and returns
        the code (or ``"cancel"``).

        Returns
        -------
        str
            The OTP code entered by the user.
        """
        self._otp_event.clear()
        await self._otp_event.wait()
        return self._otp_code

    # ------------------------------------------------------------------
    # Data conversion
    # ------------------------------------------------------------------

    def _result_to_dataframe(self, result, service_name: str) -> pd.DataFrame:
        """Convert a ``ScrapingResult`` to a DataFrame matching the existing pipeline.

        Parameters
        ----------
        result : ScrapingResult
            The scraping result from the scraper framework.
        service_name : str
            Service type (``"credit_cards"`` or ``"banks"``).

        Returns
        -------
        pd.DataFrame
            DataFrame with columns matching ``TransactionsTableFields``.
        """
        source = _SERVICE_TO_TABLE.get(service_name, "")
        rows: list[dict] = []

        for account in result.accounts:
            for txn in account.transactions:
                # Normalise date to YYYY-MM-DD
                txn_date = txn.date
                if "T" in txn_date:
                    txn_date = txn_date.split("T")[0]

                identifier = txn.identifier or ""
                unique_id = (
                    f"{self.provider_name}_{account.account_number}"
                    f"_{txn_date}_{txn.charged_amount}_{identifier}"
                )

                row_id = txn.identifier or (
                    f"{account.account_number}_{txn_date}_{txn.charged_amount}"
                )

                row = {
                    TransactionsTableFields.ID.value: row_id,
                    TransactionsTableFields.DATE.value: txn_date,
                    TransactionsTableFields.AMOUNT.value: txn.charged_amount,
                    TransactionsTableFields.DESCRIPTION.value: txn.description,
                    TransactionsTableFields.ACCOUNT_NUMBER.value: account.account_number,
                    TransactionsTableFields.TYPE.value: txn.type.value,
                    TransactionsTableFields.STATUS.value: txn.status.value,
                    TransactionsTableFields.ACCOUNT_NAME.value: self.account_name,
                    TransactionsTableFields.PROVIDER.value: self.provider_name,
                    TransactionsTableFields.CATEGORY.value: None,
                    TransactionsTableFields.TAG.value: None,
                    TransactionsTableFields.SOURCE.value: source,
                    TransactionsTableFields.UNIQUE_ID.value: unique_id,
                    TransactionsTableFields.SPLIT_ID.value: None,
                }
                rows.append(row)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Pipeline helpers (mirrored from the legacy Scraper base class)
    # ------------------------------------------------------------------

    def _save_scraped_transactions(self) -> None:
        """Persist the scraped DataFrame to the database."""
        with get_db_context() as db:
            transactions_repo = TransactionsRepository(db)
            transactions_repo.add_scraped_transactions(self._data, self._table_name)

    def _apply_auto_tagging(self) -> None:
        """Apply tagging rules to newly scraped transactions.

        Only tags transactions that do not already have a category
        (``overwrite=False``).
        """
        try:
            with get_db_context() as db:
                cat_and_tags_service = CategoriesTagsService(db)
                cat_and_tags_service.add_new_credit_card_tags()
                tagging_rules_service = TaggingRulesService(db)
                count = tagging_rules_service.apply_rules(overwrite=False)
                count += tagging_rules_service.auto_tag_credit_cards_bills()
                if count > 0:
                    logger.info(
                        "%s: %s: Auto-tagged %d transactions",
                        self.provider_name, self.account_name, count,
                    )
        except Exception as exc:
            logger.error(
                "%s: %s: Error auto-tagging — %s",
                self.provider_name, self.account_name, exc,
            )

    def _recalculate_bank_balances(self) -> None:
        """Recalculate bank balance after a successful bank scrape."""
        if self.service_name != "banks":
            return
        try:
            with get_db_context() as db:
                balance_service = BankBalanceService(db)
                balance_service.recalculate_for_account(
                    self.provider_name, self.account_name,
                )
        except Exception as exc:
            logger.error(
                "%s: %s: Error recalculating bank balance — %s",
                self.provider_name, self.account_name, exc,
            )

    def _post_save_hook(self, result) -> None:
        """Hook for subclasses to run additional logic after transactions are saved."""

    def _record_scraping_attempt(self, id_: int) -> None:
        """Update the scraping history record with the final status.

        Parameters
        ----------
        id_ : int
            Scraping history record ID (same as ``process_id``).
        """
        if self._otp_code == self.CANCEL:
            status = ScrapingHistoryRepository.CANCELED
            error_message = None
        elif self._data is not None and not self._error:
            status = ScrapingHistoryRepository.SUCCESS
            error_message = None
        else:
            status = ScrapingHistoryRepository.FAILED
            error_message = self._error or None

        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(id_, status, error_message)


class InsuranceScraperAdapter(ScraperAdapter):
    """Adapter for insurance scrapers with memo and metadata support."""

    def _result_to_dataframe(self, result, service_name: str) -> pd.DataFrame:
        """Extend base conversion to include the ``memo`` column."""
        df = super()._result_to_dataframe(result, service_name)
        if df.empty:
            return df

        memo_map: dict[str, str] = {}
        for account in result.accounts:
            for txn in account.transactions:
                if txn.memo:
                    txn_date = txn.date.split("T")[0] if "T" in txn.date else txn.date
                    row_id = txn.identifier or (
                        f"{account.account_number}_{txn_date}_{txn.charged_amount}"
                    )
                    memo_map[row_id] = txn.memo

        if memo_map:
            df["memo"] = df["id"].map(memo_map)

        return df

    def _post_save_hook(self, result) -> None:
        """Persist insurance account metadata from AccountResult.metadata."""
        from backend.models.insurance_account import InsuranceAccount

        accounts_to_upsert = [
            account.metadata
            for account in result.accounts
            if account.metadata
        ]
        if not accounts_to_upsert:
            return

        with get_db_context() as db:
            for meta in accounts_to_upsert:
                existing = db.query(InsuranceAccount).filter_by(
                    policy_id=meta["policy_id"]
                ).first()
                if existing:
                    for key, value in meta.items():
                        if key != "policy_id":
                            setattr(existing, key, value)
                else:
                    db.add(InsuranceAccount(**meta))
            db.commit()
            logger.info(
                "%s: %s: Saved metadata for %d insurance accounts",
                self.provider_name, self.account_name, len(accounts_to_upsert),
            )
