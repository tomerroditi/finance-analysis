import asyncio
import threading
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.database import get_db_context
from backend.errors import BadRequestException, EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.services.scraping_history_service import ScrapingHistoryService
from backend.scraper import ScraperAdapter, create_adapter, is_2fa_required
from backend.scraper.adapter import (
    OtpRateLimitError,
    ResendNotSupportedError,
    _active_scrapers,
    _tfa_scrapers_waiting,
)


# The server's main asyncio event loop, captured at startup (see
# ``backend.main.lifespan``). ``start_scraping_single`` runs inside a
# synchronous FastAPI route — executed in a threadpool worker thread with no
# running event loop — so it cannot use ``asyncio.create_task`` (which needs a
# loop in the *calling* thread and would raise "no running event loop",
# leaking the ``adapter.run()`` coroutine). Instead it submits the coroutine
# to this captured loop via ``asyncio.run_coroutine_threadsafe``, which is
# safe from any thread, including the loop's own thread (the async
# resend-relaunch path).
_main_loop: "asyncio.AbstractEventLoop | None" = None

# Serializes the single-flight critical section in
# ``start_scraping_single``: the ``_active_scrapers`` membership check, the
# history-row insert, and the registration of the new adapter.
#
# Without it, the check and the registration are separated by real work (a
# DB insert, adapter construction), and ``start_scraping_single`` runs in a
# FastAPI threadpool worker — so two starts for the same account landing at
# the same moment could both see an empty registry and both launch, firing
# two scrapes (and two OTP SMS) for one account. The UI now lets the user
# fire several accounts in quick succession, which makes that interleaving
# far more reachable than it was when one scrape at a time was allowed.
#
# Only ever held for local, non-awaiting work (a SQLite insert and object
# construction), never across ``_launch_adapter`` — so the async
# resend-relaunch path (``resend_2fa_code`` → ``start_scraping_single``,
# running on the event loop thread) can't stall the loop for meaningful
# time, and can't deadlock.
_launch_lock = threading.Lock()


def set_main_loop(loop: "asyncio.AbstractEventLoop | None") -> None:
    """Register the server's main event loop for launching scrapers.

    Called once from the application lifespan startup. Scraper launches are
    submitted to this loop from synchronous route handlers.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop or None
        The running event loop to schedule scraper coroutines on.
    """
    global _main_loop
    _main_loop = loop


def _launch_adapter(adapter: ScraperAdapter) -> None:
    """Schedule ``adapter.run()`` on the server's main event loop.

    Submitting via ``run_coroutine_threadsafe`` (rather than
    ``asyncio.create_task``) lets this work from a synchronous route running
    in a threadpool worker thread, which has no running loop of its own. The
    returned ``concurrent.futures.Future`` is stored on the adapter so the
    running task stays referenced for its full lifetime.

    Parameters
    ----------
    adapter : ScraperAdapter
        The adapter whose ``run()`` coroutine should be launched.
    """
    loop = _main_loop
    if loop is None:
        # No captured loop — only expected outside the running app (e.g. an
        # async caller already on a loop). Fall back to the running loop, or
        # fail loudly rather than silently dropping the scrape.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "No event loop available to launch scraper; set_main_loop() "
                "was not called at startup."
            ) from exc
    adapter._run_future = asyncio.run_coroutine_threadsafe(adapter.run(), loop)


class ScrapingService:
    """
    Service for managing data scraping operations.

    Handles launching scrapers as async tasks, tracking 2FA wait states,
    recording scraping history, and computing start dates from the last
    successful scrape. Scrapers that require 2FA are kept in the
    module-level ``_tfa_scrapers_waiting`` dict until a code is submitted
    or the process is aborted. Every running scraper (any provider) is
    also tracked in the module-level ``_active_scrapers`` dict, which
    makes ``start_scraping_single`` single-flight per account.
    """

    def __init__(self, db: Session):
        """
        Initialize the scraping service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.scraping_history_repo = ScrapingHistoryRepository(db)
        self.credentials_repo = CredentialsRepository(db)

    def get_scraping_status(self, scraping_process_id: int) -> Dict[str, str | int]:
        """
        Get the current status of a scraping process.

        Parameters
        ----------
        scraping_process_id : int
            ID of the scraping history record to query.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``status`` – status string (e.g. ``"IN_PROGRESS"``, ``"SUCCESS"``,
              ``"FAILED"``, ``"WAITING_FOR_2FA"``) or ``"unknown"`` if not found.
            - ``process_id`` – echoed back ``scraping_process_id``.
            - ``error_message`` – technical error detail if status is
              ``"FAILED"``, else ``None``. This is the provider's own message /
              exception text, meant for diagnosis — not for display as-is.
            - ``error_type`` – failure category (``INVALID_PASSWORD``,
              ``ACCOUNT_BLOCKED``, ``TIMEOUT``, ``GENERAL_ERROR``, …) the client
              maps to friendly, translated copy. ``None`` for rows recorded
              before the category was tracked, where the client falls back to
              showing ``error_message``.
        """
        status = self.scraping_history_repo.get_scraping_status(
            int(scraping_process_id)
        )
        error_message, error_type = self.scraping_history_repo.get_error(
            int(scraping_process_id)
        )
        return {
            "status": status or "unknown",
            "process_id": scraping_process_id,
            "error_message": error_message,
            "error_type": error_type,
        }

    def get_last_scrape_dates(self) -> List[Dict]:
        """
        Get last successful scrape dates for all configured accounts.
        Returns a list of dicts with service, provider, account_name, and last_scrape_date.

        Delegates to ``ScrapingHistoryService`` — the same implementation the
        scraper-free route uses, so the two can't drift.
        """
        return ScrapingHistoryService(self.db).get_last_scrape_dates()

    def get_active_scrapes(self) -> List[Dict]:
        """List every scrape currently alive in this process.

        Lets a freshly loaded client recover the scraping state it can't
        otherwise know about: which accounts are mid-scrape and which are
        parked waiting for a 2FA code. The frontend keeps scraper state in
        memory (a reload, or opening the app in a second tab, starts empty),
        and a ``waiting_for_2fa`` scraper is invisible — and therefore
        unanswerable — until the client learns its ``process_id``.

        Truth comes from the in-process registries (``_active_scrapers`` plus
        ``_tfa_scrapers_waiting``), not from the history table: rows left
        ``in_progress`` by a killed process would otherwise resurface forever
        as fake running scrapes. The registries are empty after a restart, so
        orphaned rows are correctly reported as nothing running. The DB is
        still consulted for each live adapter's current status.

        Returns
        -------
        list[dict]
            One record per live scrape with ``process_id``, ``service``,
            ``provider``, ``account_name`` and ``status`` (``in_progress`` or
            ``waiting_for_2fa``), ordered by ``process_id``. Adapters whose
            history row already reads terminal (mid-cleanup, or aborted) are
            omitted — they are no longer actionable.
        """
        active_statuses = {
            self.scraping_history_repo.IN_PROGRESS,
            self.scraping_history_repo.WAITING_FOR_2FA,
        }
        # Both registries are keyed identically, and a 2FA-waiting adapter is
        # in both — dict merge dedupes by account key, `seen` guards the
        # (unexpected) case of one adapter registered under two keys.
        adapters = {**_active_scrapers, **_tfa_scrapers_waiting}
        seen: set[int] = set()
        records: List[Dict] = []
        for adapter in adapters.values():
            if adapter.process_id in seen:
                continue
            seen.add(adapter.process_id)
            status = self.scraping_history_repo.get_scraping_status(
                adapter.process_id
            )
            if status not in active_statuses:
                continue
            records.append(
                {
                    "process_id": adapter.process_id,
                    "service": adapter.service_name,
                    "provider": adapter.provider_name,
                    "account_name": adapter.account_name,
                    "status": status,
                }
            )
        return sorted(records, key=lambda record: record["process_id"])

    def start_scraping_single(
        self,
        service: str,
        provider: str,
        account: str,
        scraping_period_days: Optional[int] = None,
        force_2fa: bool = False,
    ) -> int:
        """
        Start the scraping process for a single account as an async task.

        Records a new scraping history entry, creates a ``ScraperAdapter``,
        registers it, and launches it on the main event loop via
        ``_launch_adapter`` (using ``run_coroutine_threadsafe`` so it works
        from this synchronous route, which runs in a threadpool worker
        thread). If the provider requires 2FA, the adapter is stored in
        ``_tfa_scrapers_waiting`` until an OTP is submitted. If an account is
        already scraping (present in ``_active_scrapers``), this is a no-op
        that returns the existing run's ``process_id`` — no new history row,
        adapter, task, or SMS.

        Accounts are independent: several accounts can be scraping
        concurrently. The single-flight guard is per account only, so a user
        clicking scrape on one source after another gets parallel scrapes.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"credit_cards"``, ``"banks"``).
        provider : str
            Provider identifier (e.g. ``"isracard"``, ``"hapoalim"``).
        account : str
            Account name used to look up credentials.
        scraping_period_days : int, optional
            Number of days to scrape back from today. If ``None``, falls back
            to the automatic start date based on last scrape history.

        Returns
        -------
        int
            The ``process_id`` of the (possibly already-running) scraping
            history record.
        """
        name = f"{service} - {provider} - {account}"

        # Credential/keyring reads and the start-date lookup happen BEFORE the
        # lock so the critical section below stays free of slow I/O. Doing
        # them for a request that turns out to be a duplicate wastes a little
        # work; holding the launch lock across a keyring round trip would
        # stall every other account's launch (and the event loop, via the
        # async resend-relaunch path) instead.
        if scraping_period_days is not None:
            start_date = date.today() - timedelta(days=scraping_period_days)
        else:
            start_date = self._get_scraper_start_date(service, provider, account)
        creds = self.credentials_repo.get_credentials(service, provider, account)
        # A forced re-auth must ignore any stored OneZero long-term token so the
        # scraper falls into the interactive SMS flow; the adapter persists the
        # fresh token afterwards.
        if force_2fa:
            creds = {k: v for k, v in creds.items() if k != "otpLongTermToken"}
        requires_2fa = is_2fa_required(service, provider)

        # The check, the history insert and both registrations happen under
        # one lock so a concurrent start for the same account either returns
        # the running process_id or waits and then sees this adapter — it can
        # never slip between the check and the registration.
        with _launch_lock:
            existing = _active_scrapers.get(name)
            if existing is not None:
                return existing.process_id

            # Always start IN_PROGRESS — even for 2FA-capable providers. The
            # adapter's _otp_callback flips status to WAITING_FOR_2FA only when
            # the scraper actually awaits the OTP, so the UI never shows a 2FA
            # prompt for providers that didn't end up needing one (e.g. Hapoalim
            # from a trusted device, OneZero with a stored long-term token).
            with get_db_context() as db:
                history_repo = ScrapingHistoryRepository(db)
                process_id = history_repo.record_scrape_start(
                    service, provider, account, start_date, history_repo.IN_PROGRESS
                )

            adapter = create_adapter(
                service, provider, account, creds, start_date, process_id,
                force_2fa=force_2fa,
            )

            # Registered for ALL providers, not just 2FA ones, so any account
            # is single-flight. The adapter's run() pops this entry on
            # completion (success, failure, or cancellation).
            _active_scrapers[name] = adapter

            # Park the adapter so submit_2fa_code can resolve it later. We
            # register eagerly (rather than when the scraper actually awaits
            # OTP) because the user can submit the code immediately after
            # receiving the SMS, before the scraper has reached
            # `await on_otp_request()`. The adapter's run() cleans this entry
            # up on completion.
            if requires_2fa:
                _tfa_scrapers_waiting[name] = adapter

        # Launch only AFTER registration. `run()` executes on the event loop
        # thread, which runs concurrently with this one, and its `finally`
        # pops the registry entries by identity — so launching first let a
        # scrape that fails immediately complete its cleanup before the
        # registration above had run, leaving a dead adapter in
        # `_active_scrapers` that blocked the account until the process
        # restarted.
        _launch_adapter(adapter)

        return process_id

    def submit_2fa_code(
        self, service: str, provider: str, account: str, code: str
    ) -> None:
        """
        Submit a 2FA OTP code to an awaiting scraper.

        Pass the string ``"cancel"`` (via the scraper's ``CANCEL`` constant)
        to abort the scraping process instead.

        Parameters
        ----------
        service : str
            Service type of the waiting scraper.
        provider : str
            Provider identifier of the waiting scraper.
        account : str
            Account name of the waiting scraper.
        code : str
            OTP code to forward to the scraper, or the scraper's cancel sentinel.

        Raises
        ------
        EntityNotFoundException
            If no 2FA-waiting scraper is found for the given service/provider/account.
        """
        name = f"{service} - {provider} - {account}"
        if name not in _tfa_scrapers_waiting:
            raise EntityNotFoundException("Scraping process not found")

        adapter = _tfa_scrapers_waiting.pop(name)
        adapter.set_otp_code(code)

        # _active_scrapers is deliberately NOT popped here: the entry must
        # persist through code submission so the account stays single-flight
        # locked while the submitted code is being verified, preventing a
        # duplicate launch. The adapter's run() `finally` cleans it up once
        # the scrape actually finishes (success, failure, or cancellation).

        # Transition status from waiting_for_2fa to in_progress
        if code != ScraperAdapter.CANCEL:
            self.scraping_history_repo.update_status(
                adapter.process_id, self.scraping_history_repo.IN_PROGRESS
            )

    async def resend_2fa_code(
        self, service: str, provider: str, account: str
    ) -> dict:
        """Re-issue the OTP for an awaiting scraper without losing its process.

        Resolves the live adapter (``_active_scrapers`` first, then
        ``_tfa_scrapers_waiting``) and asks it to re-issue the OTP in place.
        Behaviour depends on the provider:

        - **Resend-capable** (OneZero — interactive SMS): the same scraper
          re-runs its OTP prepare (rate-limited), the process stays alive, and
          this returns ``{"status": "resent", "process_id": <same id>}``.
        - **Not resend-capable** (browser-based providers that raise
          ``ResendNotSupportedError``): falls back to the old behaviour —
          abort the current process and relaunch a fresh scrape with an
          automatic start date, returning
          ``{"status": "restarted", "process_id": <new id>}``.

        Parameters
        ----------
        service : str
            Service type of the waiting scraper (e.g. ``"banks"``).
        provider : str
            Provider identifier (e.g. ``"onezero"``, ``"hapoalim"``).
        account : str
            Account name of the waiting scraper.

        Returns
        -------
        dict
            ``{"status": "resent", "process_id": int}`` when the SMS was
            re-issued in place, or ``{"status": "restarted", "process_id":
            int}`` when the scrape was aborted and relaunched.

        Raises
        ------
        EntityNotFoundException
            If no active or 2FA-waiting scraper matches the given
            service/provider/account.
        BadRequestException
            If the resend is rate-limited (too many code requests too
            quickly). The message is the actionable wait-and-retry hint.
        """
        name = f"{service} - {provider} - {account}"
        adapter = _active_scrapers.get(name) or _tfa_scrapers_waiting.get(name)
        if adapter is None:
            raise EntityNotFoundException("Scraping process not found")

        try:
            await adapter.resend_otp()
        except OtpRateLimitError as err:
            raise BadRequestException(str(err)) from err
        except ResendNotSupportedError:
            # Browser providers can't re-issue mid-flow: abort the parked
            # scrape and relaunch from scratch (no period → auto start date).
            # abort_scraping_process() removes the _active_scrapers entry
            # synchronously, so start_scraping_single's single-flight check
            # sees a clean slate here — no double-registration for this account.
            self.abort_scraping_process(adapter.process_id)
            new_id = self.start_scraping_single(service, provider, account)
            return {"status": "restarted", "process_id": new_id}

        return {"status": "resent", "process_id": adapter.process_id}

    def abort_scraping_process(self, process_id: int) -> None:
        """
        Abort an in-progress or 2FA-waiting scraping process.

        If the process is waiting for a 2FA code, the scraper is cancelled
        via its OTP channel and removed from ``_tfa_scrapers_waiting``. Any
        matching entry in ``_active_scrapers`` is removed regardless of
        whether the process was 2FA-waiting, so an aborted account can be
        re-launched immediately instead of waiting for ``run()``'s
        (now-moot) cleanup. The history record is always marked ``FAILED``
        regardless.

        Parameters
        ----------
        process_id : int
            ID of the scraping history record to abort.
        """
        # Check if it's a 2FA-waiting scraper
        target_name = None
        for name, adapter in _tfa_scrapers_waiting.items():
            if adapter.process_id == process_id:
                target_name = name
                break

        if target_name:
            # Cancel the 2FA scraper
            adapter = _tfa_scrapers_waiting.pop(target_name)
            adapter.set_otp_code(ScraperAdapter.CANCEL)

        # Remove from the active-scraper registry regardless of 2FA state,
        # so the account isn't left single-flight-locked after an abort.
        active_name = None
        for name, adapter in _active_scrapers.items():
            if adapter.process_id == process_id:
                active_name = name
                break
        if active_name:
            _active_scrapers.pop(active_name, None)

        # Mark as failed in the database regardless
        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(process_id, history_repo.FAILED)

    def _get_scraper_start_date(
        self, service: str, provider: str, account: str
    ) -> datetime.date:
        """
        Calculate the start date for a scraping run.

        Uses the last successful scrape date minus 7 days as a buffer to
        catch any late-posted transactions. Falls back to 365 days ago if
        no prior successful scrape exists or the stored date cannot be parsed.

        Parameters
        ----------
        service : str
            Service type of the account.
        provider : str
            Provider identifier of the account.
        account : str
            Account name.

        Returns
        -------
        datetime.date
            Earliest date from which to fetch transactions.
        """
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
            service, provider, account
        )
        if last_scrape:
            try:
                start_date = datetime.fromisoformat(last_scrape).date() - timedelta(
                    days=7
                )
            except (ValueError, TypeError):
                start_date = date.today() - timedelta(days=365)
        else:
            start_date = date.today() - timedelta(days=365)
        return start_date

    def _collect_adapters(
        self, credentials: Dict
    ) -> tuple[Dict[str, ScraperAdapter], Dict[str, ScraperAdapter]]:
        """
        Build adapter instances for all accounts in a credentials dict.

        Parameters
        ----------
        credentials : dict
            Nested credentials dict in the form
            ``{service: {provider: {account: creds}}}``.

        Returns
        -------
        tuple[dict, dict]
            A ``(normal, tfa)`` pair where ``normal`` maps account name strings
            to adapters that do not require 2FA, and ``tfa`` maps to adapters
            that do require 2FA.

        Notes
        -----
        This method is not called by the current scraping flow (which creates
        adapters one at a time via ``start_scraping_single``) and may be unused.
        """
        normal: Dict[str, ScraperAdapter] = {}
        tfa: Dict[str, ScraperAdapter] = {}
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, acc_creds in accounts.items():
                    name = f"{service} - {provider} - {account}"
                    start = self._get_scraper_start_date(service, provider, account)
                    adapter = create_adapter(
                        service, provider, account, acc_creds, start, 0
                    )
                    if is_2fa_required(service, provider):
                        tfa[name] = adapter
                    else:
                        normal[name] = adapter
        return normal, tfa
