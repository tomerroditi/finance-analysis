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

# Recorded when a scraper reports success but returned no accounts at all.
# Isracard (:299, :361) and Max (:120, :320) pass ignore_errors=True on every
# data fetch, and HaPhoenix catches per-account failures — so an expired
# session or a changed API silently yields zero accounts. Recording that as
# SUCCESS both hid the breakage and advanced the last-successful-scrape
# watermark that the next scrape window is computed from.
NO_ACCOUNTS_ERROR = (
    "Scrape returned no accounts — the session may have expired or the "
    "provider's API may have changed. Try reconnecting the account."
)

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


def _format_key_amount(amount) -> str:
    """Render an amount for a dedup key at fixed 2-decimal precision.

    A raw float repr is not a stable key: ``0.1 + 0.2`` renders as
    ``0.30000000000000004`` while ``0.3`` renders as ``0.3``, so two runs
    that reach the same amount by different arithmetic produce different
    keys for the same transaction.

    Parameters
    ----------
    amount : float or str
        The transaction's charged amount.

    Returns
    -------
    str
        The amount at 2 decimal places, or its ``str`` form if it is not
        numeric at all.
    """
    try:
        return f"{float(amount):.2f}"
    except (TypeError, ValueError):
        return str(amount)


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

    # Sentinel passed to set_otp_code() to abort a 2FA scrape. Must stay in
    # sync with scraper.base.base_scraper.OTP_CANCEL_SENTINEL — the scraper's
    # OTP callback returns this value and short-circuits without contacting
    # the provider (see OtpCanceledError).
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
        # The event loop ``run()`` executes on, captured at its start. Lets
        # ``set_otp_code`` — invoked from a synchronous route in a threadpool
        # worker thread — wake the parked scraper by marshaling the
        # ``asyncio.Event.set()`` back onto that loop (Event is not
        # thread-safe). ``None`` until ``run()`` starts.
        self._loop: "asyncio.AbstractEventLoop | None" = None
        # The underlying scraper instance, set once ``run()`` builds it. Stays
        # ``None`` until then, so a resend that races ahead of scraper
        # construction can be rejected cleanly (see ``resend_otp``).
        self._scraper = None

        # Pipeline state
        self._data: pd.DataFrame | None = None
        self._error: str = ""
        self._table_name: str = _SERVICE_TO_TABLE.get(service_name, "")
        # Number of accounts the scraper reported, or None when the scrape
        # never produced a result. Distinguishes "an account with no
        # activity this window" (a real success) from "we fetched nothing
        # at all" (a swallowed failure). See NO_ACCOUNTS_ERROR.
        self._accounts_fetched: int | None = None

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
        # Capture the loop we're running on so set_otp_code (called from a
        # threadpool worker thread) can wake us thread-safely.
        self._loop = asyncio.get_running_loop()

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
                self._accounts_fetched = len(result.accounts)
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
            # Unregister FIRST: _record_scraping_attempt is a DB write that
            # can raise, and a raise before unregistering would leave this
            # adapter stuck in _active_scrapers — permanently blocking new
            # scrapes for the account until process restart.
            self._unregister_from_2fa_waiting()
            try:
                self._record_scraping_attempt(self.process_id)
            except Exception:
                logger.exception(
                    "%s: %s: Failed to record scraping attempt",
                    self.provider_name, self.account_name,
                )

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
        loop = self._loop
        if loop is not None and not loop.is_closed():
            # run() executes on the server's main event loop; this method is
            # called from a synchronous route in a threadpool worker thread.
            # Marshal Event.set() onto that loop so the parked scraper
            # coroutine is woken reliably — asyncio.Event is not thread-safe.
            loop.call_soon_threadsafe(self._otp_event.set)
        else:
            # No loop captured yet (adapter constructed but run() not started,
            # or unit-tested in isolation) — safe to set directly.
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

    def _iter_scraped_rows(self, result):
        """Yield ``(account, txn, txn_date, row_id, unique_id)`` per scraped row.

        Centralises dedup-key construction so the base frame and the
        insurance memo map can never disagree about a row's ``id``.

        ``id`` is the DB-visible key that
        ``TransactionsRepository.add_scraped_transactions`` dedups on, via
        the composite ``(id, provider, date, amount)``. Rows without a
        provider ``identifier`` fell back to
        ``"{account}_{date}_{amount}"``, so two genuinely distinct same-day,
        same-amount transactions collapsed onto one key. Once the first was
        stored, every overlapping re-scrape (the window reaches back 7 days)
        matched both incoming rows against it and dropped the second
        **permanently**.

        The discriminator is deliberately minimal, because the key is
        matched against rows **already in the user's database**:

        * Rows that carry a provider identifier are untouched. A repeated
          identifier means the provider itself considers the rows the same,
          and re-keying them would re-insert historical rows as duplicates.
        * The **first** identifier-less row of each
          ``(account, date, amount)`` group keeps the exact legacy string,
          including the raw float repr of the amount. Every such row already
          in the DB therefore still matches and is still deduped.
        * Only the 2nd, 3rd, … occurrence gains a ``#N`` suffix — those are
          precisely the rows that are being lost today.

        The float repr is left alone in ``id`` on purpose. Reformatting it
        (e.g. to 2dp) would change the key of *every* identifier-less row
        ever stored, re-inserting each as a duplicate on the next
        overlapping scrape. ``unique_id`` is not persisted (``unique_id`` is
        an autoincrement PK on the DB side and is excluded from the insert
        via ``TransactionBase.BASE_COLUMN_NAMES``), so it is free to use the
        deterministic 2-decimal form.

        Parameters
        ----------
        result : ScrapingResult
            The scraping result from the scraper framework.

        Yields
        ------
        tuple
            ``(account, txn, txn_date, row_id, unique_id)``.
        """
        # Occurrence counters, per scrape. Keyed on the exact tuple whose
        # collisions we are disambiguating.
        fallback_counts: dict[tuple[str, str, str], int] = {}
        unique_counts: dict[tuple[str, str, str, str], int] = {}

        for account in result.accounts:
            for txn in account.transactions:
                # Normalise date to YYYY-MM-DD
                txn_date = txn.date
                if "T" in txn_date:
                    txn_date = txn_date.split("T")[0]

                identifier = txn.identifier or ""
                key_amount = _format_key_amount(txn.charged_amount)

                unique_key = (
                    str(account.account_number), txn_date, key_amount, identifier,
                )
                unique_n = unique_counts.get(unique_key, 0) + 1
                unique_counts[unique_key] = unique_n
                unique_id = (
                    f"{self.provider_name}_{account.account_number}"
                    f"_{txn_date}_{key_amount}_{identifier}"
                )
                if unique_n > 1:
                    unique_id = f"{unique_id}#{unique_n}"

                if txn.identifier:
                    row_id = txn.identifier
                else:
                    # Legacy format preserved verbatim for the first
                    # occurrence — see the note above on backward compat.
                    row_id = (
                        f"{account.account_number}_{txn_date}"
                        f"_{txn.charged_amount}"
                    )
                    fallback_key = (
                        str(account.account_number), txn_date,
                        str(txn.charged_amount),
                    )
                    fallback_n = fallback_counts.get(fallback_key, 0) + 1
                    fallback_counts[fallback_key] = fallback_n
                    if fallback_n > 1:
                        row_id = f"{row_id}#{fallback_n}"

                yield account, txn, txn_date, row_id, unique_id

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

        for account, txn, txn_date, row_id, unique_id in self._iter_scraped_rows(
            result
        ):
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
            # An account that simply had no activity in the window is a
            # genuine success; a run that produced no accounts at all is not
            # — see NO_ACCOUNTS_ERROR.
            if self._accounts_fetched == 0:
                status = ScrapingHistoryRepository.FAILED
                error_message = NO_ACCOUNTS_ERROR
                logger.error(
                    "%s: %s: %s",
                    self.provider_name, self.account_name, NO_ACCOUNTS_ERROR,
                )
            else:
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

        # Reuse the base row-key generator so the memo map is keyed by the
        # same (discriminated) ids the frame's `id` column holds — building
        # the key a second time here is how the two drifted apart.
        memo_map: dict[str, str] = {}
        for _account, txn, _txn_date, row_id, _unique_id in self._iter_scraped_rows(
            result
        ):
            if txn.memo:
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
