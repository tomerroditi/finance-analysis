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
from backend.constants.providers import Services
from backend.constants.tables import Tables, TransactionsTableFields
from backend.database import get_db_context
from backend.errors import EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.bank_balance_service import BankBalanceService
from backend.services.tagging_rules_service import TaggingRulesService
from backend.services.tagging_service import CategoriesTagsService

logger = logging.getLogger(__name__)

# Hard ceiling on a single scrape lifecycle. Enforces the documented
# 5-minute scraping limit (see .claude/rules/backend_scraper.md → "Timeouts
# & Limits") at the adapter level, so a hung browser / provider can't pin a
# scrape coroutine indefinitely.
SCRAPE_TIMEOUT_SECONDS = 300

# NOTE: these two dicts are plain in-process, single-event-loop state —
# there is exactly one asyncio event loop per uvicorn worker, and the app
# runs a single in-process worker (see ``build/app_entry.py``). Under a
# hypothetical multi-worker deployment, each worker would get its own copy
# and these guards (single-flight lock, 2FA-waiting registry) would need
# to move to shared state (e.g. a DB row or Redis) to stay correct.

# Live adapters whose scrapers may end up awaiting an OTP. Keyed by
# ``"{service} - {provider} - {account}"`` — the same string the
# ``POST /api/scraping/2fa`` route uses to resolve the waiting adapter.
_tfa_scrapers_waiting: dict[str, "ScraperAdapter"] = {}

# Every adapter currently running for a given account, across ALL
# providers (not just 2FA-capable ones). Keyed identically to
# ``_tfa_scrapers_waiting``. ``ScrapingService.start_scraping_single``
# checks this before launching a new scrape so a second click / a
# "scrape all" fan-out can't double-launch the same account — critical
# for 2FA providers, where a second launch fires a second ``/otp/prepare``
# that supersedes the SMS code the user is already looking at.
_active_scrapers: dict[str, "ScraperAdapter"] = {}


def _import_scraper_module(name: str):
    """Import a module from the root ``scraper`` package.

    Ensures the project root is on ``sys.path`` so that the root-level
    ``scraper`` package is found instead of ``backend.scraper``.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return importlib.import_module(name)


# Re-export the root-package OTP errors so callers (e.g. ScrapingService) can
# ``from backend.scraper.adapter import ResendNotSupportedError`` without doing
# a bare ``import scraper`` (which collides with ``backend.scraper``). Resolved
# here via the helper so the collision workaround lives in exactly one place.
ResendNotSupportedError = _import_scraper_module(
    "scraper.base.base_scraper"
).ResendNotSupportedError
OtpRateLimitError = _import_scraper_module(
    "scraper.utils.otp_rate_limit"
).OtpRateLimitError

# Maps frontend service names to DB table / source column values.
_SERVICE_TO_TABLE = {
    Services.CREDIT_CARD.value: Tables.CREDIT_CARD.value,
    Services.BANK.value: Tables.BANK.value,
    Services.INSURANCE.value: Tables.INSURANCE.value,
}


def create_adapter(
    service_name: str,
    provider_name: str,
    account_name: str,
    credentials: dict,
    start_date: date,
    process_id: int,
    force_2fa: bool = False,
) -> "ScraperAdapter":
    """Create the appropriate adapter for the given service type.

    Parameters
    ----------
    service_name : str
        Service type (``"banks"``, ``"credit_cards"``, ``"insurances"``).
    provider_name, account_name, credentials, start_date, process_id
        Forwarded to the adapter constructor.
    force_2fa : bool, optional
        When ``True``, the adapter persists a refreshed long-term token after
        a successful run (see ``ScraperAdapter._persist_refreshed_otp_token``).

    Returns
    -------
    ScraperAdapter
        An ``InsuranceScraperAdapter`` for insurances, otherwise a base ``ScraperAdapter``.
    """
    cls = InsuranceScraperAdapter if service_name == Services.INSURANCE.value else ScraperAdapter
    return cls(
        service_name, provider_name, account_name, credentials,
        start_date, process_id, force_2fa=force_2fa,
    )


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
        force_2fa: bool = False,
    ):
        self.service_name = service_name
        self.provider_name = provider_name
        self.account_name = account_name
        self.credentials = credentials
        self.start_date = start_date
        self.process_id = process_id
        self.force_2fa = force_2fa

        # 2FA state
        self._otp_code: str | None = None
        self._otp_event = asyncio.Event()
        # The underlying scraper instance, set once ``run()`` builds it. Stays
        # ``None`` until then, so a resend that races ahead of scraper
        # construction can be rejected cleanly (see ``resend_otp``).
        self._scraper = None

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

        scraper = None
        try:
            scraper = self._create_scraper(create_scraper, ScraperOptions)
            # Expose the scraper so resend_otp can reach it while the
            # coroutine is parked in _otp_callback awaiting the user's code.
            self._scraper = scraper
            if scraper_is_2fa_required(self.provider_name):
                scraper.on_otp_request = self._otp_callback

            result = await asyncio.wait_for(
                scraper.scrape(), timeout=SCRAPE_TIMEOUT_SECONDS
            )

            if result.success:
                self._data = self._result_to_dataframe(result, self.service_name)
                if self._data is not None and not self._data.empty:
                    self._data = self._data.sort_values(by=["date"])
                    # TODO(perf): these are blocking sync DB writes (save,
                    # auto-tag, rebalance) that run on the event loop thread.
                    # Offloading them via run_in_executor was considered but
                    # deferred: thread-pool work is NOT cancellable by the
                    # asyncio.wait_for timeout above, so an executor hop would
                    # let DB writes outlive the 5-minute ceiling. Revisit with
                    # an explicit cancellation/cleanup story before offloading.
                    self._save_scraped_transactions()
                    self._apply_auto_tagging()
                    self._recalculate_bank_balances()
                    self._post_save_hook(result)
                self._persist_refreshed_otp_token(scraper)
            else:
                self._error = result.error_message or result.error_type or "Unknown error"
                logger.error(
                    "%s: %s: Scraping failed — %s",
                    self.provider_name, self.account_name, self._error,
                )
        except asyncio.TimeoutError:
            self._error = (
                f"Scraping exceeded the {SCRAPE_TIMEOUT_SECONDS}-second limit "
                "and was aborted"
            )
            logger.error(
                "%s: %s: Scraping timed out — %s",
                self.provider_name, self.account_name, self._error,
            )
            # wait_for cancelled scrape() mid-flight, so the scraper's own
            # terminate() in its finally may not have run — force browser
            # cleanup here to avoid leaking a Playwright process on timeout.
            if scraper is not None:
                await scraper._safe_terminate(False)
        except Exception as exc:
            self._error = str(exc)
            logger.error(
                "%s: %s: Unexpected error — %s",
                self.provider_name, self.account_name, self._error,
            )
        finally:
            self._record_scraping_attempt(self.process_id)
            self._unregister_from_2fa_waiting()

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] %s: %s: Scraping finished",
            ts, self.provider_name, self.account_name,
        )

    def _unregister_from_2fa_waiting(self) -> None:
        """Pop this adapter from the 2FA-waiting and active-scraper registries.

        Belt-and-braces cleanup: ``submit_2fa_code`` already pops the 2FA
        entry when the user provides the OTP, but if the scraper never
        awaited 2FA (Hapoalim happy path) the entry would otherwise leak.
        The active-scraper entry (registered for every provider, not just
        2FA ones) has no earlier removal point — this is its only cleanup —
        so a completed or failed scrape stops blocking a fresh launch of
        the same account.

        Pops **by identity**: an entry is removed only when it still points
        to ``self``. In the abort→relaunch race, an aborted adapter's
        ``finally`` runs after a fresh adapter has already re-registered
        under the same account key; a pop-by-name would evict that newer
        adapter and silently drop its single-flight lock (letting a
        duplicate scrape — and a duplicate OTP SMS — launch). Checking
        identity leaves the newer adapter untouched.
        """
        name = f"{self.service_name} - {self.provider_name} - {self.account_name}"
        if _tfa_scrapers_waiting.get(name) is self:
            _tfa_scrapers_waiting.pop(name, None)
        if _active_scrapers.get(name) is self:
            _active_scrapers.pop(name, None)

    def _persist_refreshed_otp_token(self, scraper) -> None:
        """Persist a freshly obtained long-term token after a forced re-auth.

        Only acts on a forced run whose scraper exposes a fresh token. Merges
        the new token into the existing credentials (so non-sensitive DB
        fields are preserved, not wiped) and upserts via CredentialsRepository.
        Any failure is logged and swallowed — it must never fail the scrape.

        Parameters
        ----------
        scraper : object
            The scraper instance that just ran; may expose
            ``refreshed_otp_long_term_token``.
        """
        if not self.force_2fa:
            return
        token = getattr(scraper, "refreshed_otp_long_term_token", None)
        if not token:
            return
        try:
            merged = {**self.credentials, "otpLongTermToken": token}
            with get_db_context() as db:
                CredentialsRepository(db).save_credentials(
                    self.service_name, self.provider_name, self.account_name, merged
                )
            logger.info(
                "%s: %s: Persisted refreshed long-term token after forced 2FA",
                self.provider_name, self.account_name,
            )
        except Exception as exc:
            logger.warning(
                "%s: %s: Failed to persist refreshed long-term token — %s",
                self.provider_name, self.account_name, exc,
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

    async def resend_otp(self) -> None:
        """Re-issue the OTP for the underlying scraper without restarting it.

        Delegates to the scraper's ``resend_otp``. This only mutates the
        provider's OTP context (e.g. OneZero's ``_otp_context``); it does not
        touch ``_otp_event`` or ``_otp_code``, so it is safe to call while the
        scraper coroutine is parked in ``_otp_callback`` awaiting the user's
        code. When the user later submits the code, the parked coroutine reads
        the freshly-updated context.

        Raises
        ------
        EntityNotFoundException
            If the scraper hasn't been built yet (the resend raced ahead of
            ``run()`` constructing it).
        ResendNotSupportedError
            If the underlying scraper can't re-issue its OTP in place (the
            caller falls back to abort + relaunch).
        OtpRateLimitError
            If the underlying prepare is rate-limited.
        """
        if self._scraper is None:
            raise EntityNotFoundException("Scraper is not ready for a resend yet")
        await self._scraper.resend_otp()

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

            if self.service_name == Services.CREDIT_CARD.value:
                return DummyCreditCardScraper(self.provider_name, self.credentials, options)
            return DummyRegularScraper(self.provider_name, self.credentials, options)

        return create_scraper_fn(self.provider_name, self.credentials, options)

    # ------------------------------------------------------------------
    # 2FA callback
    # ------------------------------------------------------------------

    async def _otp_callback(self) -> str:
        """Async callback passed to the scraper for OTP requests.

        Flips the scraping-history status to WAITING_FOR_2FA (so the UI's
        polling loop shows the OTP prompt), then waits for ``set_otp_code``
        to fire — unless a code was already delivered before this callback
        ran, in which case it returns immediately — and returns the code
        (or ``"cancel"``).

        The status flip happens lazily — only when the scraper actually
        awaits an OTP — so providers that *may* request 2FA (like Hapoalim
        from a trusted device) don't show a stale "Waiting for 2FA" state
        when no code is actually needed.

        Note: this deliberately does NOT call ``self._otp_event.clear()``.
        ``ScrapingService.start_scraping_single`` registers the adapter in
        ``_tfa_scrapers_waiting`` *before* the scraper coroutine reaches
        this callback, so a client can call ``set_otp_code`` in that gap.
        Adapters are single-use (one ``_otp_event`` per scrape), so there
        is never a second OTP round to clear stale state for — clearing
        here would instead discard a pre-delivered code's event and hang
        this coroutine until the 5-minute scrape timeout.

        Returns
        -------
        str
            The OTP code entered by the user.
        """
        self._mark_waiting_for_2fa()
        if self._otp_code is None:
            await self._otp_event.wait()
        return self._otp_code

    def _mark_waiting_for_2fa(self) -> None:
        """Update the scraping-history status to WAITING_FOR_2FA.

        Wrapped in a try/except so a transient DB failure can't crash the
        OTP flow — the scrape can still complete and report its final
        status; only the intermediate UI hint would be lost.
        """
        try:
            with get_db_context() as db:
                history_repo = ScrapingHistoryRepository(db)
                history_repo.update_status(
                    self.process_id, history_repo.WAITING_FOR_2FA
                )
        except Exception as exc:
            logger.warning(
                "%s: %s: Failed to mark waiting_for_2fa — %s",
                self.provider_name, self.account_name, exc,
            )

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
            transactions_repo.add_scraped_transactions(
                self._data,
                self._table_name,
                scrape_start_date=self.start_date.strftime("%Y-%m-%d"),
            )

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
        if self.service_name != Services.BANK.value:
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
        from backend.services.insurance_account_service import (
            InsuranceAccountService,
        )
        from backend.services.investments_service import InvestmentsService

        accounts_to_upsert = [
            account.metadata
            for account in result.accounts
            if account.metadata
        ]
        if not accounts_to_upsert:
            return

        try:
            with get_db_context() as db:
                service = InsuranceAccountService(db)
                for meta in accounts_to_upsert:
                    service.upsert(**meta)
                logger.info(
                    "%s: %s: Saved metadata for %d insurance accounts",
                    self.provider_name, self.account_name, len(accounts_to_upsert),
                )

                inv_service = InvestmentsService(db)
                for meta in accounts_to_upsert:
                    if meta.get("policy_type") != "hishtalmut":
                        continue
                    try:
                        inv_service.sync_from_insurance(meta)
                        logger.info(
                            "%s: %s: Synced hishtalmut investment for policy %s",
                            self.provider_name, self.account_name, meta["policy_id"],
                        )
                    except Exception:
                        logger.exception(
                            "%s: %s: Failed to sync hishtalmut investment for policy %s",
                            self.provider_name, self.account_name, meta["policy_id"],
                        )
        except Exception as exc:
            logger.error(
                "%s: %s: Error saving insurance metadata — %s",
                self.provider_name, self.account_name, exc,
            )
