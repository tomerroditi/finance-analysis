import asyncio
import logging
import sys
import threading
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.database import get_db_context
from backend.errors import BadRequestException, EntityNotFoundException
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.scraper import ScraperAdapter, create_adapter, is_2fa_required
from backend.scraper.adapter import (
    OtpRateLimitError,
    ResendNotSupportedError,
    _active_scrapers,
    _tfa_scrapers_waiting,
    scraper_registry_key,
)
from backend.services.scraping_history_service import ScrapingHistoryService

logger = logging.getLogger(__name__)

# Scrapers run on their own event loop, on a dedicated daemon thread, never on
# the server's. Browser scrapers launch Playwright's driver with
# ``asyncio.create_subprocess_exec``, which on Windows only a
# ``ProactorEventLoop`` supports — and uvicorn hands the server a
# ``SelectorEventLoop`` on Windows whenever it runs with ``--reload`` (its
# ``use_subprocess`` mode), so every browser scrape died with
# ``initialize failed: NotImplementedError``. Owning the loop makes the
# launch mode irrelevant, and keeps a scrape's blocking DB writes (save,
# auto-tag, rebalance) off the thread that serves requests.
#
# Routes reach this loop only through thread-safe hand-offs:
# ``run_coroutine_threadsafe`` to launch, ``Future.cancel`` to abort,
# ``call_soon_threadsafe`` to deliver an OTP, and ``ScraperAdapter.resend_otp``
# for a resend.
_scraper_loop: "asyncio.AbstractEventLoop | None" = None
_scraper_loop_lock = threading.Lock()
# Scrape tasks still in flight, so shutdown can cancel exactly the scrapes —
# not Playwright's own tasks on the same loop, which the scrapes still need to
# close their browsers. Touched only from the scraper loop's thread.
_running_scrapes: "set[asyncio.Task]" = set()

# How long shutdown waits for cancelled scrapes to close their browsers and
# record their outcome before the loop is stopped regardless.
_SHUTDOWN_GRACE_SECONDS = 10

# Serialises the single-flight critical section of ``start_scraping_single``:
# the ``_active_scrapers`` re-check, the history-row insert, and the
# registration + launch that follow it.
#
# ``start_scraping_single`` is a *synchronous* route handler, so FastAPI runs
# it in a threadpool worker — two requests for the same account genuinely run
# in parallel on two OS threads. Without this lock both could pass the
# registry check and each launch a scrape: two history rows, two adapters and,
# on a 2FA provider, two OTP SMS for one account. (Being free of ``await``
# between the check and the insert only rules out *coroutine* interleaving,
# which was never the exposure here.)
#
# Held across the launch, not just the registration, so an adapter that fails
# to schedule can be rolled back before any other thread observes it. The slow
# preparation — keyring reads, the start-date lookup — deliberately happens
# outside, so a launch for one account never blocks another behind a keyring
# round trip.
_launch_lock = threading.Lock()


def _new_scraper_loop() -> asyncio.AbstractEventLoop:
    """Create an event loop that can spawn subprocesses on every platform.

    Returns
    -------
    asyncio.AbstractEventLoop
        A ``ProactorEventLoop`` on Windows, the platform default elsewhere.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def get_scraper_loop() -> asyncio.AbstractEventLoop:
    """Return the scraper event loop, starting its thread on first use.

    Returns
    -------
    asyncio.AbstractEventLoop
        The running loop every ``ScraperAdapter.run()`` is scheduled on.
    """
    global _scraper_loop
    with _scraper_loop_lock:
        if _scraper_loop is None:
            loop = _new_scraper_loop()
            threading.Thread(
                target=loop.run_forever, name="scraper-loop", daemon=True
            ).start()
            _scraper_loop = loop
        return _scraper_loop


async def shutdown_scraper_loop() -> None:
    """Cancel in-flight scrapes and stop the scraper loop.

    Cancelling (rather than just stopping the loop) lets each adapter close
    its browser and record the run as canceled, instead of leaving a
    Playwright process behind and a history row stuck in progress.
    """
    global _scraper_loop
    with _scraper_loop_lock:
        loop, _scraper_loop = _scraper_loop, None
    if loop is None:
        return

    async def cancel_running_scrapes() -> None:
        tasks = list(_running_scrapes)
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=_SHUTDOWN_GRACE_SECONDS)
            if pending:
                logger.warning(
                    "%d scrape(s) did not finish cancelling before shutdown",
                    len(pending),
                )

    try:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(cancel_running_scrapes(), loop)
        )
    finally:
        loop.call_soon_threadsafe(loop.stop)


async def _run_tracked(adapter: ScraperAdapter) -> None:
    """Run ``adapter.run()`` as a task shutdown can find and cancel.

    Parameters
    ----------
    adapter : ScraperAdapter
        The adapter to run.
    """
    task = asyncio.current_task()
    _running_scrapes.add(task)
    try:
        await adapter.run()
    finally:
        _running_scrapes.discard(task)


def _launch_adapter(adapter: ScraperAdapter) -> None:
    """Schedule ``adapter.run()`` on the scraper event loop.

    Safe from any thread — the synchronous launch route runs in a threadpool
    worker, and the async resend-relaunch path runs on the server loop. The
    returned ``concurrent.futures.Future`` is stored on the adapter so the
    running task stays referenced for its full lifetime and can be cancelled
    by an abort.

    ``run_coroutine_threadsafe`` does not carry the caller's context, so the
    adapter re-applies the demo mode it captured at construction (see
    ``ScraperAdapter._apply_demo_context``). Do not assume the coroutine
    inherits anything context-local from this call site.

    Parameters
    ----------
    adapter : ScraperAdapter
        The adapter whose ``run()`` coroutine should be launched.
    """
    adapter._run_future = asyncio.run_coroutine_threadsafe(
        _run_tracked(adapter), get_scraper_loop()
    )


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

    def get_scraping_status(self, scraping_process_id: int) -> dict[str, str | int]:
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

    def get_last_scrape_dates(self) -> list[dict]:
        """Get last successful scrape dates for all configured accounts.

        Delegates to :class:`ScrapingHistoryService`, which carries the
        implementation so the same answer is available without the scraper
        stack. Kept here as a thin pass-through because callers already hold
        a ``ScrapingService``.

        Returns
        -------
        list[dict]
            Records with ``service``, ``provider``, ``account_name`` and
            ``last_scrape_date``.
        """
        return ScrapingHistoryService(self.db).get_last_scrape_dates()

    def get_active_scrapes(self) -> list[dict[str, str | int]]:
        """List the scrapes currently running for the caller's demo mode.

        The UI's in-progress state lives in a React hook that is torn down
        whenever the user leaves the Data Sources page, so it needs a way to
        re-learn what is still running on mount. ``_active_scrapers`` is the
        authoritative answer: an adapter is inserted there when a scrape is
        launched and popped by ``run()``'s ``finally`` on success, failure, or
        cancellation.

        Deliberately sourced from the in-memory registry rather than from
        history rows with an ``in_progress`` status. A scrape interrupted by a
        server restart leaves its row stuck at ``in_progress`` forever with no
        live adapter behind it — surfacing those would pin a permanent, and
        un-abortable, "scraping…" card in the UI.

        Scoped to the caller's demo mode: a demo client must not be shown (or
        handed the ``process_id`` of) a real-mode client's in-flight scrape,
        and vice versa.

        Returns
        -------
        list[dict]
            One entry per live scrape, with ``process_id``, ``service``,
            ``provider``, ``account_name``, and ``status`` (``"in_progress"``
            or ``"waiting_for_2fa"``). Empty when nothing is running.
        """
        demo = AppConfig().is_demo_mode
        active: list[dict[str, str | int]] = []
        for adapter in list(_active_scrapers.values()):
            if adapter.demo_mode != demo:
                continue
            status = self.scraping_history_repo.get_scraping_status(adapter.process_id)
            active.append(
                {
                    "process_id": adapter.process_id,
                    "service": adapter.service_name,
                    "provider": adapter.provider_name,
                    "account_name": adapter.account_name,
                    "status": status or self.scraping_history_repo.IN_PROGRESS,
                }
            )
        return active

    def start_scraping_single(
        self,
        service: str,
        provider: str,
        account: str,
        scraping_period_days: int | None = None,
        force_2fa: bool = False,
    ) -> int:
        """
        Start the scraping process for a single account as an async task.

        Records a new scraping history entry, creates a ``ScraperAdapter``,
        and launches it on the scraper event loop via ``_launch_adapter`` (using
        ``run_coroutine_threadsafe`` so it works from this synchronous route,
        which runs in a threadpool worker thread). If the provider requires
        2FA, the adapter is stored in ``_tfa_scrapers_waiting`` until an OTP
        is submitted. If an account is already scraping (present in
        ``_active_scrapers``), this is a no-op that returns the existing
        run's ``process_id`` — no new history row, adapter, task, or SMS.

        Single-flight holds under true parallelism, not just against
        interleaved coroutines: this runs in a threadpool worker, so
        ``_launch_lock`` serialises the check-insert-register-launch section
        across threads. Concurrent calls for the same account return the same
        ``process_id``; concurrent calls for *different* accounts each launch,
        queueing only for the brief moment the section is held.

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
        key = scraper_registry_key(AppConfig().is_demo_mode, service, provider, account)
        # Unlocked fast path: an obviously-running account costs no lock and no
        # keyring read. The authoritative check is the one inside the lock
        # below — this one may be stale the moment it returns.
        existing = _active_scrapers.get(key)
        if existing is not None:
            return existing.process_id

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

        with _launch_lock:
            # Re-check under the lock. The fast path above raced: another
            # thread may have registered this account while this one was busy
            # reading credentials. Whoever gets here second adopts the winner's
            # run rather than starting a second one, discarding the credentials
            # it prepared — wasted work, but never a duplicate SMS.
            existing = _active_scrapers.get(key)
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
                service,
                provider,
                account,
                creds,
                start_date,
                process_id,
                force_2fa=force_2fa,
            )

            # Register BEFORE launching. ``run()`` executes on the scraper
            # loop's own thread and pops both registries in its ``finally``,
            # by identity. Launching first means a scrape that fails
            # immediately — a dead browser, bad credentials — can reach that
            # cleanup while this key is still absent: the pop finds nothing,
            # no-ops, and the registration below then installs an adapter that
            # has already finished, wedging the account until restart.
            #
            # Registered for ALL providers, not just 2FA ones, so any account
            # is single-flight.
            _active_scrapers[key] = adapter

            # Park the adapter so submit_2fa_code can resolve it later. We
            # register eagerly (rather than when the scraper actually awaits
            # OTP) because the user can submit the code immediately after
            # receiving the SMS, before the scraper has reached
            # `await on_otp_request()`. The adapter's run() cleans this entry
            # up on completion.
            if requires_2fa:
                _tfa_scrapers_waiting[key] = adapter

            try:
                _launch_adapter(adapter)
            except Exception:
                # Nothing is going to run, so nothing will ever pop these.
                # Undo by identity for the same reason run() does: only this
                # adapter's own entries are ours to remove.
                if _active_scrapers.get(key) is adapter:
                    _active_scrapers.pop(key, None)
                if _tfa_scrapers_waiting.get(key) is adapter:
                    _tfa_scrapers_waiting.pop(key, None)
                with get_db_context() as db:
                    failed_repo = ScrapingHistoryRepository(db)
                    failed_repo.record_scrape_end(
                        process_id,
                        failed_repo.FAILED,
                        error_message="Failed to launch the scraper",
                        error_type="GENERAL_ERROR",
                    )
                raise

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
        key = scraper_registry_key(AppConfig().is_demo_mode, service, provider, account)
        if key not in _tfa_scrapers_waiting:
            raise EntityNotFoundException("Scraping process not found")

        adapter = _tfa_scrapers_waiting.pop(key)
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

    async def resend_2fa_code(self, service: str, provider: str, account: str) -> dict:
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
        key = scraper_registry_key(AppConfig().is_demo_mode, service, provider, account)
        adapter = _active_scrapers.get(key) or _tfa_scrapers_waiting.get(key)
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
        (now-moot) cleanup, and its ``run()`` future is cancelled so a
        scraper that is *not* parked on an OTP (a plain browser scrape mid
        fetch) actually stops instead of running to completion behind the
        user's back. The history record is marked ``CANCELED`` regardless —
        the adapter's own bookkeeping never overwrites that status.

        Scoped to the caller's demo mode. ``process_id`` is a per-database
        autoincrement, so demo ``5`` and real ``5`` are different scrapes;
        matching on the number alone would let one client abort another
        client's in-flight scraper. The history write is already
        mode-correct — ``get_db_context()`` resolves per context.

        Parameters
        ----------
        process_id : int
            ID of the scraping history record to abort.
        """
        # ``process_id`` is a per-database autoincrement, so demo 5 and real 5
        # are different scrapes. Match on the caller's mode as well, or an
        # abort from one client would cancel another client's in-flight
        # scraper that merely shares the number.
        demo = AppConfig().is_demo_mode

        # Check if it's a 2FA-waiting scraper
        target_key = None
        for candidate_key, adapter in _tfa_scrapers_waiting.items():
            if adapter.process_id == process_id and adapter.demo_mode == demo:
                target_key = candidate_key
                break

        if target_key:
            # Cancel the 2FA scraper
            adapter = _tfa_scrapers_waiting.pop(target_key)
            adapter.set_otp_code(ScraperAdapter.CANCEL)

        # Remove from the active-scraper registry regardless of 2FA state,
        # so the account isn't left single-flight-locked after an abort.
        active_key = None
        for candidate_key, adapter in _active_scrapers.items():
            if adapter.process_id == process_id and adapter.demo_mode == demo:
                active_key = candidate_key
                break
        if active_key:
            adapter = _active_scrapers.pop(active_key)
            # The OTP sentinel only reaches a scraper parked on an OTP; a
            # non-2FA scrape (or a 2FA one already past its OTP) needs the
            # coroutine itself cancelled. The cancellation is marshalled onto
            # the loop by the future's own callback, so this is thread-safe
            # from the sync route.
            run_future = getattr(adapter, "_run_future", None)
            if run_future is not None:
                run_future.cancel()

        # Mark as canceled in the database regardless
        with get_db_context() as db:
            history_repo = ScrapingHistoryRepository(db)
            history_repo.record_scrape_end(process_id, history_repo.CANCELED)

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
