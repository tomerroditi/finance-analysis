"""Adapter bridging the async Python scraper framework to the backend pipeline.

Owns one scrape's lifecycle: building the provider scraper (or its demo
dummy), the 2FA dance, the 5-minute ceiling, user aborts and the
``scraping_history`` row. A successful ``ScrapingResult`` is handed to
``backend.services.scrape_ingestion``, which turns it into stored rows.

Note: imports from the root ``scraper`` package use ``_import_scraper_module``
to avoid the naming collision with ``backend.scraper``.
"""

import asyncio
import concurrent.futures
import contextlib
import datetime
import importlib
import logging
import os
import sys
from collections.abc import Callable, Iterator
from datetime import date
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pandas as pd

from backend.config import AppConfig
from backend.constants.providers import Services
from backend.database import get_db_context
from backend.errors import EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.services.credentials_service import CredentialsService
from backend.services.scrape_ingestion import ingestion_for
from backend.utils.log_sanitize import scrub

if TYPE_CHECKING:
    from scraper.base.base_scraper import BaseScraper, ScraperOptions

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

# NOTE: these two dicts are plain in-process state — every scrape runs on the
# one scraper event loop (``scraping_service.get_scraper_loop``), and the app
# runs a single in-process worker (see ``build/app_entry.py``). Under a
# hypothetical multi-worker deployment, each worker would get its own copy
# and these guards (single-flight lock, 2FA-waiting registry) would need
# to move to shared state (e.g. a DB row or Redis) to stay correct.

#: Registry key: ``(demo_mode, service, provider, account)``.
#:
#: Demo Mode is per-client, so one backend process can be running a demo
#: scrape and a real scrape for the *same* account name at the same time —
#: demo seed credentials use names like ``"Main Account"`` and
#: ``"Family Card"``, which a real user can plausibly reuse. The mode is
#: therefore part of the key, not an assumption about the process.
ScraperRegistryKey = tuple[bool, str, str, str]


def scraper_registry_key(
    demo_mode: bool, service: str, provider: str, account: str
) -> ScraperRegistryKey:
    """Build the registry key for one account under one demo mode.

    A tuple rather than an interpolated string: the previous
    ``f"{service} - {provider} - {account}"`` form let a user-supplied
    account name containing the delimiter land on another account's key.

    Parameters
    ----------
    demo_mode : bool
        Whether the scrape belongs to a demo-mode client. Callers serving a
        request pass ``AppConfig().is_demo_mode``; an adapter passes its own
        captured ``self.demo_mode``, which is the mode of the client that
        launched it.
    service : str
        Service type (e.g. ``"credit_cards"``, ``"banks"``).
    provider : str
        Provider identifier (e.g. ``"isracard"``, ``"hapoalim"``).
    account : str
        User-assigned account label.

    Returns
    -------
    ScraperRegistryKey
        Key into :data:`_active_scrapers` and :data:`_tfa_scrapers_waiting`.
    """
    return (demo_mode, service, provider, account)


# Live adapters whose scrapers may end up awaiting an OTP. Keyed by
# :func:`scraper_registry_key` — the ``POST /api/scraping/2fa`` route passes
# the service/provider/account components and the service rebuilds the key,
# so the key shape never crosses the API boundary.
_tfa_scrapers_waiting: dict[ScraperRegistryKey, "ScraperAdapter"] = {}

# Every adapter currently running for a given account, across ALL
# providers (not just 2FA-capable ones). Keyed identically to
# ``_tfa_scrapers_waiting``. ``ScrapingService.start_scraping_single``
# checks this before launching a new scrape so a second click / a
# "scrape all" fan-out can't double-launch the same account — critical
# for 2FA providers, where a second launch fires a second ``/otp/prepare``
# that supersedes the SMS code the user is already looking at.
_active_scrapers: dict[ScraperRegistryKey, "ScraperAdapter"] = {}


def _import_scraper_module(name: str) -> ModuleType:
    """Import a module from the root ``scraper`` package.

    Ensures the project root is on ``sys.path`` so that the root-level
    ``scraper`` package is found instead of ``backend.scraper``.
    """
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
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
# Single renderer for "what was this exception", shared with the scraper package
# so a failure reads the same whether it was caught inside a scraper or out here.
_describe_exception = _import_scraper_module(
    "scraper.base.base_scraper"
).describe_exception


def create_adapter(
    service_name: str,
    provider_name: str,
    account_name: str,
    credentials: dict[str, Any],
    start_date: date,
    process_id: int,
    force_2fa: bool = False,
) -> "ScraperAdapter":
    """Create the adapter for one scrape.

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
        The adapter, its ingestion pipeline chosen by ``service_name``.
    """
    return ScraperAdapter(
        service_name,
        provider_name,
        account_name,
        credentials,
        start_date,
        process_id,
        force_2fa=force_2fa,
    )


class ScraperAdapter:
    """Bridges the scraper framework to the backend services pipeline.

    Runs an async scraper from the ``scraper`` package and hands a
    successful ``ScrapingResult`` to its ``ScrapeIngestion``.

    Parameters
    ----------
    service_name : str
        Service type (``"credit_cards"``, ``"banks"`` or ``"insurances"``).
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
        credentials: dict[str, Any],
        start_date: date,
        process_id: int,
        force_2fa: bool = False,
    ) -> None:
        self.service_name = service_name
        self.provider_name = provider_name
        self.account_name = account_name
        self.credentials = credentials
        self.start_date = start_date
        self.process_id = process_id
        self.force_2fa = force_2fa

        # Identity prefix on every log line this adapter emits. Includes the
        # process id because that IS the `scraping_history.id` — without it,
        # matching a log line to the failed row it explains meant eyeballing
        # provider + account + timestamp, which is ambiguous the moment an
        # account is scraped twice in a day.
        self._log_id = f"scrape#{process_id} {provider_name}/{account_name}"

        # 2FA state
        self._otp_code: str | None = None
        self._otp_event = asyncio.Event()
        # The event loop ``run()`` executes on, captured at its start. Lets
        # ``set_otp_code`` — invoked from a synchronous route in a threadpool
        # worker thread — wake the parked scraper by marshaling the
        # ``asyncio.Event.set()`` back onto that loop (Event is not
        # thread-safe). ``None`` until ``run()`` starts.
        self._loop: asyncio.AbstractEventLoop | None = None
        # The underlying scraper instance, set once ``run()`` builds it. Stays
        # ``None`` until then, so a resend that races ahead of scraper
        # construction can be rejected cleanly (see ``resend_otp``).
        self._scraper: BaseScraper | None = None
        # ``concurrent.futures.Future`` for the scheduled ``run()`` coroutine,
        # set by ``scraping_service._launch_adapter``. Cancelling it is how an
        # abort reaches a scraper that is NOT parked on an OTP — the only
        # other abort channel is the OTP sentinel, which a non-2FA scraper
        # never reads.
        self._run_future: concurrent.futures.Future | None = None
        # Set when ``run()`` is cancelled mid-flight (user abort), so the
        # history row records CANCELED rather than a synthetic failure.
        self._canceled = False

        # Pipeline state
        self._data: pd.DataFrame | None = None
        # Technical failure detail — the provider's own message, HTTP body or
        # exception text. Recorded verbatim for diagnosis.
        self._error: str = ""
        # Failure category (``ScrapingResult.error_type``), recorded alongside
        # so the UI can render friendly translated copy without the technical
        # text having to double as a user-facing message.
        self._error_type: str = ""
        self._ingestion = ingestion_for(
            service_name, provider_name, account_name, start_date, self._log_id
        )
        # Number of accounts the scraper reported, or None when the scrape
        # never produced a result. Distinguishes "an account with no
        # activity this window" (a real success) from "we fetched nothing
        # at all" (a swallowed failure). See NO_ACCOUNTS_ERROR.
        self._accounts_fetched: int | None = None

        # Demo mode is context-local and does NOT survive the hand-off in
        # scraping_service._launch_adapter (run_coroutine_threadsafe starts
        # the coroutine in a context copied on the scraper loop, not ours), so
        # capture it here — inside the request — and re-apply it in run().
        self.demo_mode = AppConfig().is_demo_mode

    @contextlib.contextmanager
    def _apply_demo_context(self) -> Iterator[None]:
        """Bind the captured demo mode for the duration of the block.

        Yields
        ------
        None
            The block runs with ``AppConfig().is_demo_mode`` equal to the
            mode captured when this adapter was constructed. Restores the
            previous value on exit so the event loop's context is not left
            mutated for unrelated tasks.
        """
        config = AppConfig()
        token = config.set_demo_mode(self.demo_mode)
        try:
            yield
        finally:
            config.reset_demo_mode(token)

    async def run(self) -> None:
        """Run the scraper and feed results through the backend pipeline.

        Imports and instantiates the appropriate scraper, converts the
        ``ScrapingResult`` to a DataFrame, saves transactions, applies
        auto-tagging, and recalculates bank balances. Always records the
        outcome in the scraping history table.

        Runs entirely inside the demo-mode context captured at construction,
        so both the database this writes to and the choice of dummy versus
        real provider match the client that launched the scrape.
        """
        # Capture the loop we're running on so set_otp_code (called from a
        # threadpool worker thread) can wake us thread-safely.
        self._loop = asyncio.get_running_loop()

        with self._apply_demo_context():
            _scraper_pkg = _import_scraper_module("scraper")
            create_scraper = _scraper_pkg.create_scraper
            scraper_is_2fa_required = _scraper_pkg.is_2fa_required
            ScraperOptions = _import_scraper_module(
                "scraper.base.base_scraper"
            ).ScraperOptions

            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                "[%s] %s: Scraping started (from %s)",
                ts,
                scrub(self._log_id),
                self.start_date,
            )

            scraper: BaseScraper | None = None
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
                    # Blocking sync DB writes: they stall the scraper loop —
                    # and so any concurrent scrape — but never the server,
                    # which runs on its own loop (see ScrapeIngestion.ingest).
                    self._data = self._ingestion.ingest(result)
                else:
                    self._error_type = result.error_type or "GENERAL_ERROR"
                    self._error = (
                        result.error_message
                        or f"the {self.provider_name} scraper reported "
                        f"{self._error_type} with no further detail"
                    )
                    logger.error(
                        "%s: Scraping failed — [%s] %s",
                        scrub(self._log_id),
                        scrub(self._error_type),
                        scrub(self._error),
                    )
            except TimeoutError:
                self._error_type = "TIMEOUT"
                self._error = (
                    f"Scraping exceeded the {SCRAPE_TIMEOUT_SECONDS}-second limit "
                    "and was aborted"
                )
                logger.error(
                    "%s: Scraping timed out — %s",
                    scrub(self._log_id),
                    scrub(self._error),
                )
                # wait_for cancelled scrape() mid-flight, so the scraper's own
                # terminate() in its finally may not have run — force browser
                # cleanup here to avoid leaking a Playwright process on timeout.
                if scraper is not None:
                    await scraper._safe_terminate(False)
            except asyncio.CancelledError:
                # The user aborted (``ScrapingService.abort_scraping_process``
                # cancels ``_run_future``). The scraper's own terminate() was
                # skipped by the cancellation, so release the browser here;
                # the ``finally`` below still records the outcome and frees
                # the registries, then the cancellation propagates.
                self._canceled = True
                logger.info("%s: Scraping canceled by the user", scrub(self._log_id))
                if scraper is not None:
                    await scraper._safe_terminate(False)
                raise
            except Exception as exc:
                self._error_type = "GENERAL_ERROR"
                self._error = _describe_exception(exc)
                logger.error(
                    "%s: Unexpected error — %s",
                    scrub(self._log_id),
                    scrub(self._error),
                )
            finally:
                # Persist before anything that can raise, and regardless of how the
                # scrape ended. A token is minted the moment login succeeds, so a
                # later fetch_data failure (or the 5-minute timeout) must not throw
                # it away — doing so costs the user another SMS for a failure that
                # had nothing to do with authentication, and every wasted SMS walks
                # them toward the provider's own rate limit.
                if scraper is not None:
                    self._persist_refreshed_otp_token(scraper)

                # Unregister FIRST: _record_scraping_attempt is a DB write that
                # can raise, and a raise before unregistering would leave this
                # adapter stuck in _active_scrapers — permanently blocking new
                # scrapes for the account until process restart.
                self._unregister_from_2fa_waiting()
                try:
                    self._record_scraping_attempt(self.process_id)
                except Exception:
                    logger.exception(
                        "%s: Failed to record scraping attempt",
                        scrub(self._log_id),
                    )

                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    "[%s] %s: Scraping finished",
                    ts,
                    scrub(self._log_id),
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
        # Keyed on the mode captured at construction, not the ambient one, so
        # the cleanup can only ever reach this adapter's own client's entry.
        key = scraper_registry_key(
            self.demo_mode, self.service_name, self.provider_name, self.account_name
        )
        if _tfa_scrapers_waiting.get(key) is self:
            _tfa_scrapers_waiting.pop(key, None)
        if _active_scrapers.get(key) is self:
            _active_scrapers.pop(key, None)

    def _persist_refreshed_otp_token(self, scraper: "BaseScraper") -> None:
        """Persist a freshly obtained long-term token, however it was obtained.

        A long-term token lets later scrapes skip the SMS round trip entirely,
        so it is worth keeping whenever one is minted — not only on a forced
        re-auth. This used to return early unless ``force_2fa`` was set, which
        silently discarded the token from a *first* connect: the provider's
        credential form has no ``otpLongTermToken`` field (it cannot — the token
        does not exist until a scrape has run), and this method is the only
        writer, so nothing else could save it. The result was an SMS prompt on
        every single scrape unless the user happened to use the force-2FA path.

        Merges the new token into the existing credentials (so non-sensitive DB
        fields are preserved, not wiped) and upserts via CredentialsRepository.
        Any failure is logged and swallowed — it must never fail the scrape.

        Parameters
        ----------
        scraper : BaseScraper
            The scraper instance that just ran; may expose
            ``refreshed_otp_long_term_token``.
        """
        token = getattr(scraper, "refreshed_otp_long_term_token", None)
        if not token:
            return
        if token == self.credentials.get("otpLongTermToken"):
            # Unchanged token — skip the Keyring write rather than rewrite the
            # same secret on every scrape.
            return
        try:
            # The password is deliberately left out: ``get_credentials`` always
            # materialises a ``password`` key (empty when none is stored), and
            # re-sending it would rewrite — or blank — the Keyring entry on
            # every token refresh. Omitted fields leave the Keyring untouched.
            merged = {k: v for k, v in self.credentials.items() if k != "password"}
            merged["otpLongTermToken"] = token
            with get_db_context() as db:
                CredentialsRepository(db).save_credentials(
                    self.service_name, self.provider_name, self.account_name, merged
                )
            # Written past the service, whose cache would go on holding the old
            # token.
            CredentialsService.clear_cache()
            logger.info(
                "%s: Persisted long-term token; later scrapes can skip the SMS",
                scrub(self._log_id),
            )
        except Exception as exc:
            logger.warning(
                "%s: Failed to persist refreshed long-term token — %s",
                scrub(self._log_id),
                scrub(exc),
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
            # run() executes on the scraper event loop; this method is called
            # from a synchronous route in a threadpool worker thread.
            # Marshal Event.set() onto that loop so the parked scraper
            # coroutine is woken reliably — asyncio.Event is not thread-safe.
            loop.call_soon_threadsafe(self._otp_event.set)
        else:
            # No loop captured yet (adapter constructed but run() not started,
            # or unit-tested in isolation) — safe to set directly.
            self._otp_event.set()

    async def resend_otp(self) -> None:
        """Re-issue the OTP for the underlying scraper without restarting it.

        Delegates to the scraper's ``resend_otp``, run on the loop ``run()``
        executes on: the caller is on the server loop, but the scraper's
        HTTP client and browser belong to the scraper loop and cannot be
        driven from another one. This only mutates the
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
        loop = self._loop
        if loop is None or loop is asyncio.get_running_loop():
            await self._scraper.resend_otp()
            return
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(self._scraper.resend_otp(), loop)
        )

    def _create_scraper(
        self,
        create_scraper_fn: Callable[
            [str, dict[str, Any], "ScraperOptions"], "BaseScraper"
        ],
        options_cls: type["ScraperOptions"],
    ) -> "BaseScraper":
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
                return DummyCreditCardScraper(
                    self.provider_name, self.credentials, options
                )
            return DummyRegularScraper(self.provider_name, self.credentials, options)

        return create_scraper_fn(self.provider_name, self.credentials, options)

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
                "%s: Failed to mark waiting_for_2fa — %s",
                scrub(self._log_id),
                scrub(exc),
            )

    def _record_scraping_attempt(self, id_: int) -> None:
        """Update the scraping history record with the final status.

        Parameters
        ----------
        id_ : int
            Scraping history record ID (same as ``process_id``).
        """
        error_type = None
        if self._canceled or self._otp_code == self.CANCEL:
            status = ScrapingHistoryRepository.CANCELED
            error_message = None
        elif self._data is not None and not self._error:
            # An account that simply had no activity in the window is a
            # genuine success; a run that produced no accounts at all is not
            # — see NO_ACCOUNTS_ERROR.
            if self._accounts_fetched == 0:
                status = ScrapingHistoryRepository.FAILED
                error_message = NO_ACCOUNTS_ERROR
                error_type = "NO_ACCOUNTS"
                logger.error(
                    "%s: %s",
                    scrub(self._log_id),
                    NO_ACCOUNTS_ERROR,
                )
            else:
                status = ScrapingHistoryRepository.SUCCESS
                error_message = None
        else:
            status = ScrapingHistoryRepository.FAILED
            error_message = self._error or None
            error_type = self._error_type or "GENERAL_ERROR"

        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            # An abort records CANCELED synchronously from the route, but the
            # cancellation only lands at the coroutine's next ``await`` — a
            # scrape already past its last await finishes and would otherwise
            # flip the user's explicit cancel back to SUCCESS or FAILED.
            if (
                status != ScrapingHistoryRepository.CANCELED
                and history_repo.get_scraping_status(id_)
                == ScrapingHistoryRepository.CANCELED
            ):
                logger.info(
                    "%s: Already recorded as canceled; keeping that status",
                    scrub(self._log_id),
                )
                return
            history_repo.record_scrape_end(id_, status, error_message, error_type)
