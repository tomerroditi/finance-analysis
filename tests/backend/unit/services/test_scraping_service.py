"""Tests for ScrapingService."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

import backend.services.scraping_service as ss
from backend.errors import EntityNotFoundException
from backend.services.scraping_service import ScrapingService


@pytest.fixture(autouse=True)
def reset_tfa_waiting():
    """Clear _tfa_scrapers_waiting between tests."""
    ss._tfa_scrapers_waiting.clear()
    yield
    ss._tfa_scrapers_waiting.clear()


@pytest.fixture(autouse=True)
def reset_active_scrapers():
    """Clear _active_scrapers between tests."""
    ss._active_scrapers.clear()
    yield
    ss._active_scrapers.clear()


@pytest.fixture(autouse=True)
def reset_credentials_singleton():
    """Reset CredentialsRepository singleton between tests."""
    from backend.repositories.credentials_repository import CredentialsRepository

    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False
    yield
    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False


@pytest.fixture
def mock_db():
    """Provide a mock database session."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create a ScrapingService with mocked repositories."""
    with patch(
        "backend.services.scraping_service.ScrapingHistoryRepository"
    ) as MockHistoryRepo, patch(
        "backend.services.scraping_service.CredentialsRepository"
    ) as MockCredsRepo:
        svc = ScrapingService(mock_db)
        svc.scraping_history_repo = MockHistoryRepo.return_value
        svc.credentials_repo = MockCredsRepo.return_value
    return svc


class TestScrapingServiceStatus:
    """Tests for scraping status retrieval methods."""

    def test_get_scraping_status(self, service):
        """Verify the status dict carries status, process_id, and both error fields."""
        service.scraping_history_repo.get_scraping_status.return_value = "in_progress"
        service.scraping_history_repo.get_error.return_value = (None, None)

        result = service.get_scraping_status(42)

        assert result == {
            "status": "in_progress",
            "process_id": 42,
            "error_message": None,
            "error_type": None,
        }
        service.scraping_history_repo.get_scraping_status.assert_called_once_with(42)
        service.scraping_history_repo.get_error.assert_called_once_with(42)

    def test_get_scraping_status_reports_type_alongside_detail(self, service):
        """The failure category travels with the technical detail, not instead of it.

        The client needs both: the category selects the translated message it
        shows, and the detail is the provider's own text kept available for
        debugging. Collapsing them into one string is what forced the raw text
        to double as the user-facing message.
        """
        service.scraping_history_repo.get_scraping_status.return_value = "failed"
        service.scraping_history_repo.get_error.return_value = (
            "login invalid_password: detected on https://x.test/login",
            "INVALID_PASSWORD",
        )

        result = service.get_scraping_status(7)

        assert result["error_type"] == "INVALID_PASSWORD"
        assert "https://x.test/login" in result["error_message"]

    def test_get_scraping_status_unknown(self, service):
        """Verify status is 'unknown' when repository returns None."""
        service.scraping_history_repo.get_scraping_status.return_value = None
        service.scraping_history_repo.get_error.return_value = (None, None)

        result = service.get_scraping_status(99)

        assert result["status"] == "unknown"
        assert result["process_id"] == 99

    def test_get_last_scrape_dates_delegates_to_history_service(self, service):
        """The public method must keep answering, via the shared implementation.

        The query itself lives in ``ScrapingHistoryService`` so the scraper-free
        route can reuse it (see ``test_scraping_history_service.py`` for its
        behaviour); this pins that ``ScrapingService`` still exposes it and does
        not grow a second copy.
        """
        expected = [
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Checking",
                "last_scrape_date": "2026-02-18",
            },
        ]
        history_service = MagicMock()
        history_service.get_last_scrape_dates.return_value = expected

        with patch(
            "backend.services.scraping_service.ScrapingHistoryService",
            return_value=history_service,
        ):
            assert service.get_last_scrape_dates() == expected


class TestScrapingServiceStart:
    """Tests for starting scraping processes."""

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_single(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Verify start_scraping_single returns a process_id and launches an async task."""
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 7

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            process_id = service.start_scraping_single("banks", "hapoalim", "Main")

        assert process_id == 7
        mock_create_adapter.assert_called_once()
        mock_asyncio.run_coroutine_threadsafe.assert_called_once()

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_creates_history(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Verify that a history record is created via get_db_context."""
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 10

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("credit_cards", "isracard", "Acc1")

        mock_history_repo.record_scrape_start.assert_called_once()
        call_args = mock_history_repo.record_scrape_start.call_args
        assert call_args[0][0] == "credit_cards"
        assert call_args[0][1] == "isracard"
        assert call_args[0][2] == "Acc1"

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_2fa_adds_to_waiting(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Verify adapter is added to _tfa_scrapers_waiting when 2FA is required."""
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        mock_history_repo.record_scrape_start.return_value = 15

        mock_adapter = mock_create_adapter.return_value

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "leumi", "MyAcc")

        expected_key = "banks - leumi - MyAcc"
        assert expected_key in ss._tfa_scrapers_waiting
        assert ss._tfa_scrapers_waiting[expected_key] is mock_adapter

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_2fa_starts_in_progress(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """2FA-capable scrapes start in IN_PROGRESS (status flips lazily later).

        The adapter's _otp_callback transitions the status to WAITING_FOR_2FA
        only when the scraper actually awaits the OTP — so the UI doesn't
        show a 2FA prompt for providers like Hapoalim that don't always need
        one.
        """
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        mock_history_repo.record_scrape_start.return_value = 20

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "hapoalim", "MyAcc")

        mock_history_repo.record_scrape_start.assert_called_once()
        # 5th positional arg of record_scrape_start is the initial status
        call_args = mock_history_repo.record_scrape_start.call_args
        assert call_args[0][4] == "in_progress"

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_force_2fa_strips_token_and_forwards_flag(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """force_2fa=True drops otpLongTermToken from creds and passes the flag."""
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {
            "email": "e", "password": "p", "phoneNumber": "+1", "otpLongTermToken": "OLD",
        }
        mock_history_repo = MagicMock()
        mock_history_repo.record_scrape_start.return_value = 7

        @contextmanager
        def fake_ctx():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_ctx
        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "onezero", "Acc", force_2fa=True)

        creds_arg = mock_create_adapter.call_args.args[3]
        assert "otpLongTermToken" not in creds_arg
        assert creds_arg["email"] == "e"
        assert mock_create_adapter.call_args.kwargs["force_2fa"] is True

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_default_keeps_token_and_flag_false(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Without force_2fa the stored token is preserved and the flag is False."""
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {
            "email": "e", "password": "p", "otpLongTermToken": "OLD",
        }
        mock_history_repo = MagicMock()
        mock_history_repo.record_scrape_start.return_value = 8

        @contextmanager
        def fake_ctx():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_ctx
        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "onezero", "Acc")

        creds_arg = mock_create_adapter.call_args.args[3]
        assert creds_arg["otpLongTermToken"] == "OLD"
        assert mock_create_adapter.call_args.kwargs["force_2fa"] is False


class TestScrapingServiceLaunchFromSyncContext:
    """The scraper launch must work from a synchronous route handler.

    ``POST /api/scraping/start`` is a sync ``def`` route, which FastAPI runs
    in a threadpool worker thread with no running event loop. The launch
    therefore cannot use ``asyncio.create_task`` — it requires a loop in the
    *calling* thread and raises ``RuntimeError: no running event loop``,
    leaving ``adapter.run()`` an un-awaited coroutine (the RuntimeWarning
    that surfaced on a real OneZero scrape). It must submit the coroutine to
    the main loop captured at startup. Regression test for that bug.
    """

    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_launch_from_threadpool_thread_actually_runs_coroutine(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, service
    ):
        """A launch from a no-event-loop worker thread executes adapter.run()."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}

        ran = threading.Event()

        async def fake_run():
            ran.set()

        mock_adapter = MagicMock()
        mock_adapter.process_id = 77
        mock_adapter.run = fake_run
        mock_create_adapter.return_value = mock_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 77

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        # A real event loop, spinning in a background thread, stands in for
        # the server's main uvicorn loop captured at startup.
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        ss.set_main_loop(loop)

        try:
            with patch(
                "backend.services.scraping_service.ScrapingHistoryRepository",
                return_value=mock_history_repo,
            ):
                # Run start_scraping_single in a worker thread with no event
                # loop, exactly as FastAPI runs a sync route. On the buggy
                # create_task path this raises RuntimeError here.
                with ThreadPoolExecutor(max_workers=1) as pool:
                    process_id = pool.submit(
                        service.start_scraping_single, "banks", "onezero", "Acc"
                    ).result(timeout=5)

            assert process_id == 77
            assert ran.wait(timeout=5), "adapter.run() was never scheduled/executed"
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=5)
            loop.close()
            ss.set_main_loop(None)


class TestScrapingServiceSingleFlight:
    """A second start_scraping_single call for the same account is a no-op.

    Guards against duplicate scrapes of the same account — for 2FA
    providers in particular, a second launch would fire a second
    /otp/prepare, superseding the SMS code the user is already looking at
    and risking a provider-side fraud block from the burst.
    """

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_second_call_returns_first_process_id_without_new_adapter(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """A duplicate call for the same account returns the existing
        process_id and does not create a second adapter or task."""
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        mock_history_repo.record_scrape_start.return_value = 30

        first_adapter = MagicMock()
        first_adapter.process_id = 30
        mock_create_adapter.return_value = first_adapter

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            first_id = service.start_scraping_single("banks", "onezero", "Acc1")
            second_id = service.start_scraping_single("banks", "onezero", "Acc1")

        assert first_id == 30
        assert second_id == 30
        # Only the first call created an adapter / history row / task.
        mock_create_adapter.assert_called_once()
        mock_history_repo.record_scrape_start.assert_called_once()
        mock_asyncio.run_coroutine_threadsafe.assert_called_once()

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_registers_in_active_scrapers_for_non_2fa_providers_too(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """The active-scraper registry guards ALL providers, not just 2FA ones."""
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 31

        mock_adapter = mock_create_adapter.return_value
        mock_adapter.process_id = 31

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("credit_cards", "isracard", "Card1")

        expected_key = "credit_cards - isracard - Card1"
        assert expected_key in ss._active_scrapers
        assert ss._active_scrapers[expected_key] is mock_adapter

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_different_accounts_both_proceed(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Two different accounts are unaffected by each other's registration."""
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.side_effect = [40, 41]

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            first_id = service.start_scraping_single("banks", "hapoalim", "AccA")
            second_id = service.start_scraping_single("banks", "hapoalim", "AccB")

        assert first_id == 40
        assert second_id == 41
        assert mock_create_adapter.call_count == 2
        assert mock_asyncio.run_coroutine_threadsafe.call_count == 2


class TestScrapingService2FA:
    """Tests for 2FA code submission."""

    def test_submit_2fa_code(self, service):
        """Verify set_otp_code is called on the correct adapter."""
        mock_adapter = MagicMock()
        name = "credit_cards - isracard - Main"
        ss._tfa_scrapers_waiting[name] = mock_adapter

        service.submit_2fa_code("credit_cards", "isracard", "Main", "123456")

        mock_adapter.set_otp_code.assert_called_once_with("123456")

    def test_submit_2fa_code_not_found(self, service):
        """Verify EntityNotFoundException raised for unknown scraper."""
        with pytest.raises(EntityNotFoundException):
            service.submit_2fa_code("banks", "unknown", "NoAccount", "000000")


class TestScrapingServiceAbort:
    """Tests for aborting scraping processes."""

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_scraping_process(self, mock_get_db_ctx, service):
        """Verify CANCEL is sent and history is recorded as failed."""
        mock_adapter = MagicMock()
        mock_adapter.process_id = 20
        mock_adapter.CANCEL = "cancel"
        ss._tfa_scrapers_waiting["banks - leumi - Acc"] = mock_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.abort_scraping_process(20)

        mock_adapter.set_otp_code.assert_called_once_with("cancel")
        mock_history_repo.record_scrape_end.assert_called_once_with(20, "failed")
        assert "banks - leumi - Acc" not in ss._tfa_scrapers_waiting

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_scraping_process_pops_active_scrapers(self, mock_get_db_ctx, service):
        """Aborting a 2FA-waiting scraper also removes it from _active_scrapers."""
        mock_adapter = MagicMock()
        mock_adapter.process_id = 21
        mock_adapter.CANCEL = "cancel"
        ss._tfa_scrapers_waiting["banks - leumi - Acc2"] = mock_adapter
        ss._active_scrapers["banks - leumi - Acc2"] = mock_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.abort_scraping_process(21)

        assert "banks - leumi - Acc2" not in ss._active_scrapers

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_2fa_scraper(self, mock_get_db_ctx, service):
        """Verify CANCEL is sent to 2FA adapter via set_otp_code."""
        mock_adapter = MagicMock()
        mock_adapter.process_id = 55
        mock_adapter.CANCEL = "cancel"
        ss._tfa_scrapers_waiting["credit_cards - max - Card1"] = mock_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.abort_scraping_process(55)

        mock_adapter.set_otp_code.assert_called_once_with("cancel")
        assert "credit_cards - max - Card1" not in ss._tfa_scrapers_waiting

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_non_2fa_process_records_failure(self, mock_get_db_ctx, service):
        """Verify abort records failure in history even when process is not in _tfa_scrapers_waiting."""
        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.abort_scraping_process(999)

        mock_history_repo.record_scrape_end.assert_called_once_with(999, "failed")
        assert len(ss._tfa_scrapers_waiting) == 0


class TestScrapingServiceCustomPeriod:
    """Tests for custom scraping period date calculation."""

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_single_with_custom_period(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Verify scraping_period_days overrides automatic start date calculation."""
        from datetime import date, timedelta

        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 42

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "hapoalim", "Main", scraping_period_days=30)

        call_args = mock_history_repo.record_scrape_start.call_args
        expected_start = date.today() - timedelta(days=30)
        assert call_args[0][3] == expected_start

        # _get_scraper_start_date was NOT called (custom period takes precedence)
        service.scraping_history_repo.get_last_successful_scrape_date.assert_not_called()


class TestScrapingServiceStartDate:
    """Tests for _get_scraper_start_date logic."""

    def test_get_scraper_start_date_with_iso_date(self, service):
        """Verify ISO format date string is parsed and 7-day buffer applied."""
        from datetime import datetime, timedelta

        service.scraping_history_repo.get_last_successful_scrape_date.return_value = (
            "2026-02-20T10:30:00"
        )

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        expected = datetime.fromisoformat("2026-02-20T10:30:00").date() - timedelta(days=7)
        assert result == expected

    def test_get_scraper_start_date_invalid_date_falls_back(self, service):
        """Verify invalid date string falls back to 365 days ago."""
        from datetime import date, timedelta

        service.scraping_history_repo.get_last_successful_scrape_date.return_value = (
            "not-a-date"
        )

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        expected = date.today() - timedelta(days=365)
        assert result == expected

    def test_get_scraper_start_date_no_prior_scrape(self, service):
        """Verify None last scrape falls back to 365 days ago."""
        from datetime import date, timedelta

        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        expected = date.today() - timedelta(days=365)
        assert result == expected


class TestScrapingServiceCollectAdapters:
    """Tests for _collect_adapters method."""

    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_collect_adapters_separates_normal_and_2fa(
        self, mock_is_2fa, mock_create_adapter, service
    ):
        """Verify adapters are separated into normal and 2FA dicts."""
        mock_is_2fa.side_effect = lambda svc, prov: prov == "onezero"
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_adapter = MagicMock()
        mock_create_adapter.return_value = mock_adapter

        credentials = {
            "banks": {
                "hapoalim": {"Main": {"userCode": "test"}},
                "onezero": {"Account1": {"email": "test@test.com"}},
            }
        }

        normal, tfa = service._collect_adapters(credentials)

        assert "banks - hapoalim - Main" in normal
        assert "banks - onezero - Account1" in tfa
        assert len(normal) == 1
        assert len(tfa) == 1

    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_collect_adapters_multiple_services(
        self, mock_is_2fa, mock_create_adapter, service
    ):
        """Verify adapters are created for accounts across multiple services."""
        mock_is_2fa.return_value = False
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_adapter = MagicMock()
        mock_create_adapter.return_value = mock_adapter

        credentials = {
            "banks": {"hapoalim": {"Checking": {"userCode": "abc"}}},
            "credit_cards": {"isracard": {"Card1": {"id": "123"}}},
        }

        normal, tfa = service._collect_adapters(credentials)

        assert len(normal) == 2
        assert len(tfa) == 0
        assert mock_create_adapter.call_count == 2


def _make_adapter(process_id, service_name, provider_name, account_name):
    """Build a stand-in adapter with the identity fields the registries expose."""
    adapter = MagicMock()
    adapter.process_id = process_id
    adapter.service_name = service_name
    adapter.provider_name = provider_name
    adapter.account_name = account_name
    return adapter


class TestScrapingServiceActiveScrapes:
    """Tests for get_active_scrapes — the client's cold-load recovery path.

    Scraper state lives only in the browser's memory, so a reload (or a
    second tab) has no process ids: a running scrape looks idle and a
    2FA-waiting scrape is unanswerable. This endpoint is how the client
    re-adopts them.
    """

    def test_reports_running_and_waiting_scrapes(self, service):
        """Every live adapter is reported with its current DB status."""
        service.scraping_history_repo.IN_PROGRESS = "in_progress"
        service.scraping_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        running = _make_adapter(11, "banks", "hapoalim", "Checking")
        waiting = _make_adapter(12, "banks", "onezero", "Daily")
        ss._active_scrapers["banks - hapoalim - Checking"] = running
        ss._active_scrapers["banks - onezero - Daily"] = waiting
        ss._tfa_scrapers_waiting["banks - onezero - Daily"] = waiting
        service.scraping_history_repo.get_scraping_status.side_effect = (
            lambda pid: "in_progress" if pid == 11 else "waiting_for_2fa"
        )

        result = service.get_active_scrapes()

        assert result == [
            {
                "process_id": 11,
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Checking",
                "status": "in_progress",
            },
            {
                "process_id": 12,
                "service": "banks",
                "provider": "onezero",
                "account_name": "Daily",
                "status": "waiting_for_2fa",
            },
        ]

    def test_reports_a_2fa_waiting_adapter_once(self, service):
        """An adapter in both registries yields exactly one record.

        A 2FA-capable scraper is registered in ``_active_scrapers`` *and*
        ``_tfa_scrapers_waiting``; reporting it twice would have the client
        track (and poll) the same process under one card twice.
        """
        service.scraping_history_repo.IN_PROGRESS = "in_progress"
        service.scraping_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        adapter = _make_adapter(20, "banks", "onezero", "Daily")
        ss._active_scrapers["banks - onezero - Daily"] = adapter
        ss._tfa_scrapers_waiting["banks - onezero - Daily"] = adapter
        service.scraping_history_repo.get_scraping_status.return_value = (
            "waiting_for_2fa"
        )

        result = service.get_active_scrapes()

        assert len(result) == 1
        assert result[0]["process_id"] == 20

    def test_omits_adapters_whose_run_already_finished(self, service):
        """A terminal history row is not an active scrape.

        An adapter can still be registered while its ``run()`` finally block
        is unwinding. Reporting it would have a freshly loaded client show a
        finished scrape as running — and poll a process that will never move.
        """
        service.scraping_history_repo.IN_PROGRESS = "in_progress"
        service.scraping_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        ss._active_scrapers["banks - hapoalim - Checking"] = _make_adapter(
            30, "banks", "hapoalim", "Checking"
        )
        service.scraping_history_repo.get_scraping_status.return_value = "success"

        assert service.get_active_scrapes() == []

    def test_empty_when_nothing_is_registered(self, service):
        """Orphaned in_progress rows from a killed process report nothing.

        Truth is the in-process registries, not the history table: a scrape
        interrupted by a crash leaves its row ``in_progress`` forever, and a
        DB-driven implementation would resurrect it as a running scrape on
        every load, with a process id nothing can ever answer.
        """
        service.scraping_history_repo.IN_PROGRESS = "in_progress"
        service.scraping_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"

        assert service.get_active_scrapes() == []
        service.scraping_history_repo.get_scraping_status.assert_not_called()


class TestScrapingServiceLaunchOrdering:
    """The adapter must be registered BEFORE its coroutine is launched."""

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_registers_before_launching(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """``run()`` executes on the event-loop thread, concurrently with this
        one, and its cleanup pops the registries by identity. Launching first
        let a scrape that failed immediately finish its cleanup before the
        registration ran — leaving a dead adapter in ``_active_scrapers``
        that blocked every later scrape of that account until restart.
        """
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 50

        adapter = _make_adapter(50, "banks", "hapoalim", "Main")
        mock_create_adapter.return_value = adapter

        registered_at_launch = {}

        def record_registry_state(*_args, **_kwargs):
            registered_at_launch["value"] = (
                ss._active_scrapers.get("banks - hapoalim - Main") is adapter
            )
            return MagicMock()

        mock_asyncio.run_coroutine_threadsafe.side_effect = record_registry_state

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            service.start_scraping_single("banks", "hapoalim", "Main")

        assert registered_at_launch["value"] is True

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_concurrent_starts_for_one_account_launch_once(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Two simultaneous starts for the same account launch a single scrape.

        ``start_scraping_single`` runs in a FastAPI threadpool worker, and the
        UI now lets the user fire sources in quick succession — so two calls
        for one account really can interleave. Without the launch lock both
        could pass the registry check and launch, firing two scrapes and two
        OTP SMS for one account. The delay injected into the history insert
        forces exactly that interleaving.
        """
        import threading

        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        ids = iter([61, 62])

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"

        def slow_record_start(*_args, **_kwargs):
            # Stand-in for the real DB insert: any pause here is a window for
            # the other thread to slip between the check and the registration.
            import time

            time.sleep(0.05)
            return next(ids)

        mock_history_repo.record_scrape_start.side_effect = slow_record_start
        mock_create_adapter.side_effect = lambda *a, **k: _make_adapter(
            a[5], "banks", "onezero", "Acc"
        )

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        results = []

        def start():
            results.append(service.start_scraping_single("banks", "onezero", "Acc"))

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            threads = [threading.Thread(target=start) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert mock_history_repo.record_scrape_start.call_count == 1
        assert mock_asyncio.run_coroutine_threadsafe.call_count == 1
        # Both callers get the one live process id.
        assert results == [61, 61]

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_concurrent_starts_for_different_accounts_both_launch(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """The lock is a per-account guard, not a global scraping mutex.

        Accounts scrape in parallel — the user clicks one source after another
        and expects both to run — so concurrent starts for *different*
        accounts must both go through.
        """
        import threading

        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        counter = iter([71, 72, 73])
        mock_history_repo.record_scrape_start.side_effect = lambda *a, **k: next(counter)
        mock_create_adapter.side_effect = lambda *a, **k: _make_adapter(
            a[5], a[0], a[1], a[2]
        )

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        def start(account):
            service.start_scraping_single("banks", "hapoalim", account)

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            threads = [
                threading.Thread(target=start, args=(account,))
                for account in ("AccA", "AccB", "AccC")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert mock_asyncio.run_coroutine_threadsafe.call_count == 3
        assert len(ss._active_scrapers) == 3
