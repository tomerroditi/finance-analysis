"""Tests for ScrapingService."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import backend.services.scraping_service as ss
from backend.errors import EntityNotFoundException
from backend.scraper.adapter import ScraperAdapter, scraper_registry_key
from backend.services.scraping_service import ScrapingService


@pytest.fixture(autouse=True)
def reset_registries():
    """Clear both module-level registries between tests."""
    ss._tfa_scrapers_waiting.clear()
    ss._active_scrapers.clear()
    yield
    ss._tfa_scrapers_waiting.clear()
    ss._active_scrapers.clear()


@pytest.fixture
def service():
    """Create a ScrapingService with mocked repositories."""
    with patch(
        "backend.services.scraping_service.ScrapingHistoryRepository"
    ) as MockHistoryRepo, patch(
        "backend.services.scraping_service.CredentialsRepository"
    ) as MockCredsRepo:
        svc = ScrapingService(MagicMock())
        svc.scraping_history_repo = MockHistoryRepo.return_value
        svc.credentials_repo = MockCredsRepo.return_value
    return svc


@pytest.fixture
def launch():
    """Stub the event-loop hand-off so no coroutine is ever scheduled.

    Patching ``_launch_adapter`` (rather than the whole ``asyncio`` module)
    keeps the rest of the service's asyncio usage real and lets a test
    assert exactly which adapter was handed to the loop.
    """
    with patch("backend.services.scraping_service._launch_adapter") as mock:
        yield mock


@pytest.fixture
def history_repo():
    """Patch the history repository the service builds inside ``get_db_context``.

    ``start_scraping_single`` and ``abort_scraping_process`` open their own
    DB context rather than using the injected session, so the repository
    they see is this one — not ``service.scraping_history_repo``.
    """
    repo = MagicMock()
    repo.IN_PROGRESS = "in_progress"
    repo.WAITING_FOR_2FA = "waiting_for_2fa"
    repo.FAILED = "failed"
    repo.CANCELED = "canceled"

    @contextmanager
    def fake_db_context():
        yield MagicMock()

    with patch(
        "backend.services.scraping_service.get_db_context",
        side_effect=fake_db_context,
    ), patch(
        "backend.services.scraping_service.ScrapingHistoryRepository",
        return_value=repo,
    ):
        yield repo


@pytest.fixture
def create_adapter():
    """Stub adapter construction so no scraper is ever built."""
    with patch("backend.services.scraping_service.create_adapter") as mock:
        yield mock


@pytest.fixture
def is_2fa_required():
    """Stub the 2FA-provider lookup; tests set ``return_value`` as needed."""
    with patch(
        "backend.services.scraping_service.is_2fa_required", return_value=False
    ) as mock:
        yield mock


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

    def test_get_last_scrape_dates(self, service):
        """Verify last scrape dates are fetched for all configured accounts."""
        service.credentials_repo.list_accounts.return_value = [
            {"service": "credit_cards", "provider": "isracard", "account_name": "Main"},
            {"service": "banks", "provider": "hapoalim", "account_name": "Checking"},
        ]
        service.scraping_history_repo.get_last_successful_scrape_date.side_effect = [
            "2026-02-18",
            None,
        ]

        result = service.get_last_scrape_dates()

        assert len(result) == 2
        assert result[0] == {
            "service": "credit_cards",
            "provider": "isracard",
            "account_name": "Main",
            "last_scrape_date": "2026-02-18",
        }
        assert result[1]["last_scrape_date"] is None


class TestScrapingServiceStart:
    """Tests for starting scraping processes."""

    def test_start_records_history_builds_adapter_and_launches(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """A launch records IN_PROGRESS, builds one adapter from the stored
        credentials and start date, hands it to the loop and registers it as
        the account's single-flight holder — nothing is parked for 2FA."""
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None
        history_repo.record_scrape_start.return_value = 7
        adapter = create_adapter.return_value
        adapter.process_id = 7

        process_id = service.start_scraping_single("credit_cards", "isracard", "Acc1")

        assert process_id == 7
        expected_start = date.today() - timedelta(days=365)
        history_repo.record_scrape_start.assert_called_once_with(
            "credit_cards", "isracard", "Acc1", expected_start, "in_progress"
        )
        create_adapter.assert_called_once_with(
            "credit_cards", "isracard", "Acc1", {"user": "test"}, expected_start, 7,
            force_2fa=False,
        )
        launch.assert_called_once_with(adapter)
        key = scraper_registry_key(False, "credit_cards", "isracard", "Acc1")
        assert ss._active_scrapers[key] is adapter
        assert key not in ss._tfa_scrapers_waiting

    def test_start_2fa_provider_parks_adapter_but_still_starts_in_progress(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """A 2FA-capable provider is parked for a later code, yet its row starts
        IN_PROGRESS: the adapter's OTP callback flips it to WAITING_FOR_2FA only
        when the scraper actually asks, so Hapoalim from a trusted device never
        shows a spurious prompt."""
        is_2fa_required.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None
        history_repo.record_scrape_start.return_value = 15
        adapter = create_adapter.return_value

        service.start_scraping_single("banks", "hapoalim", "MyAcc")

        assert history_repo.record_scrape_start.call_args.args[4] == "in_progress"
        key = scraper_registry_key(False, "banks", "hapoalim", "MyAcc")
        assert ss._tfa_scrapers_waiting[key] is adapter
        assert ss._active_scrapers[key] is adapter

    def test_force_2fa_strips_token_and_forwards_flag(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """force_2fa=True drops otpLongTermToken from creds and passes the flag."""
        is_2fa_required.return_value = True
        service.credentials_repo.get_credentials.return_value = {
            "email": "e", "password": "p", "phoneNumber": "+1", "otpLongTermToken": "OLD",
        }
        history_repo.record_scrape_start.return_value = 7

        service.start_scraping_single("banks", "onezero", "Acc", force_2fa=True)

        creds_arg = create_adapter.call_args.args[3]
        assert "otpLongTermToken" not in creds_arg
        assert creds_arg["email"] == "e"
        assert create_adapter.call_args.kwargs["force_2fa"] is True

    def test_default_keeps_token_and_flag_false(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """Without force_2fa the stored token is preserved and the flag is False."""
        is_2fa_required.return_value = True
        service.credentials_repo.get_credentials.return_value = {
            "email": "e", "password": "p", "otpLongTermToken": "OLD",
        }
        history_repo.record_scrape_start.return_value = 8

        service.start_scraping_single("banks", "onezero", "Acc")

        creds_arg = create_adapter.call_args.args[3]
        assert creds_arg["otpLongTermToken"] == "OLD"
        assert create_adapter.call_args.kwargs["force_2fa"] is False


class TestScrapingServiceSingleFlight:
    """A second start_scraping_single call for the same account is a no-op.

    Guards against duplicate scrapes of the same account — for 2FA
    providers in particular, a second launch would fire a second
    /otp/prepare, superseding the SMS code the user is already looking at
    and risking a provider-side fraud block from the burst.
    """

    def test_second_call_returns_first_process_id_without_new_adapter(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """A duplicate call for the same account returns the existing
        process_id and does not create a second adapter, row or task."""
        is_2fa_required.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None
        history_repo.record_scrape_start.return_value = 30
        create_adapter.return_value.process_id = 30

        first_id = service.start_scraping_single("banks", "onezero", "Acc1")
        second_id = service.start_scraping_single("banks", "onezero", "Acc1")

        assert first_id == 30
        assert second_id == 30
        create_adapter.assert_called_once()
        history_repo.record_scrape_start.assert_called_once()
        launch.assert_called_once()

    def test_registers_in_active_scrapers_for_non_2fa_providers_too(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """The active-scraper registry guards ALL providers, not just 2FA ones."""
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None
        history_repo.record_scrape_start.return_value = 31
        adapter = create_adapter.return_value
        adapter.process_id = 31

        service.start_scraping_single("credit_cards", "isracard", "Card1")

        key = scraper_registry_key(False, "credit_cards", "isracard", "Card1")
        assert ss._active_scrapers[key] is adapter

    def test_different_accounts_both_proceed(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """Two different accounts are unaffected by each other's registration."""
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None
        history_repo.record_scrape_start.side_effect = [40, 41]

        first_id = service.start_scraping_single("banks", "hapoalim", "AccA")
        second_id = service.start_scraping_single("banks", "hapoalim", "AccB")

        assert first_id == 40
        assert second_id == 41
        assert create_adapter.call_count == 2
        assert launch.call_count == 2


class TestScrapingService2FA:
    """Tests for 2FA code submission."""

    def test_submit_code_wakes_adapter_and_transitions_to_in_progress(self, service):
        """A submitted code reaches the parked adapter, un-parks it from the 2FA
        registry (a second submit must 404, not re-wake it), keeps the
        single-flight lock in ``_active_scrapers`` while the code is verified,
        and flips the row back to IN_PROGRESS so the UI drops the prompt."""
        adapter = MagicMock()
        adapter.process_id = 12
        key = scraper_registry_key(False, "credit_cards", "isracard", "Main")
        ss._tfa_scrapers_waiting[key] = adapter
        ss._active_scrapers[key] = adapter

        service.submit_2fa_code("credit_cards", "isracard", "Main", "123456")

        adapter.set_otp_code.assert_called_once_with("123456")
        assert key not in ss._tfa_scrapers_waiting
        assert ss._active_scrapers[key] is adapter
        service.scraping_history_repo.update_status.assert_called_once_with(
            12, service.scraping_history_repo.IN_PROGRESS
        )

    def test_submit_cancel_does_not_flip_status_back_to_in_progress(self, service):
        """The cancel sentinel is forwarded but the row is left for the adapter
        to record as CANCELED — an IN_PROGRESS flip would show a spinner for a
        scrape the user just killed."""
        adapter = MagicMock()
        adapter.process_id = 12
        key = scraper_registry_key(False, "credit_cards", "isracard", "Main")
        ss._tfa_scrapers_waiting[key] = adapter

        service.submit_2fa_code(
            "credit_cards", "isracard", "Main", ScraperAdapter.CANCEL
        )

        adapter.set_otp_code.assert_called_once_with(ScraperAdapter.CANCEL)
        service.scraping_history_repo.update_status.assert_not_called()

    def test_submit_2fa_code_not_found(self, service):
        """Verify EntityNotFoundException raised for unknown scraper."""
        with pytest.raises(EntityNotFoundException):
            service.submit_2fa_code("banks", "unknown", "NoAccount", "000000")


class TestScrapingServiceAbort:
    """Tests for aborting scraping processes."""

    @staticmethod
    def _adapter(process_id: int) -> MagicMock:
        """Build a stand-in adapter matching the caller's (real) mode."""
        adapter = MagicMock()
        adapter.process_id = process_id
        adapter.demo_mode = False
        return adapter

    def test_abort_2fa_waiting_scraper_cancels_via_otp_and_records_canceled(
        self, service, history_repo
    ):
        """A scraper parked on an OTP is woken with the cancel sentinel, dropped
        from BOTH registries (so the account can relaunch immediately) and its
        row is recorded CANCELED — not FAILED, which is a provider error."""
        adapter = self._adapter(20)
        key = scraper_registry_key(False, "banks", "leumi", "Acc")
        ss._tfa_scrapers_waiting[key] = adapter
        ss._active_scrapers[key] = adapter

        service.abort_scraping_process(20)

        adapter.set_otp_code.assert_called_once_with(ScraperAdapter.CANCEL)
        adapter._run_future.cancel.assert_called_once_with()
        assert key not in ss._tfa_scrapers_waiting
        assert key not in ss._active_scrapers
        history_repo.record_scrape_end.assert_called_once_with(20, "canceled")

    def test_abort_in_flight_non_2fa_scrape_cancels_its_future(
        self, service, history_repo
    ):
        """A scraper that is NOT parked on an OTP never reads the sentinel, so
        the abort must cancel the coroutine itself. Previously only the
        registry entry was dropped and the browser kept scraping to completion
        behind the user's back, then overwrote the status."""
        adapter = self._adapter(21)
        key = scraper_registry_key(False, "credit_cards", "max", "Card1")
        ss._active_scrapers[key] = adapter

        service.abort_scraping_process(21)

        adapter._run_future.cancel.assert_called_once_with()
        adapter.set_otp_code.assert_not_called()
        assert key not in ss._active_scrapers
        history_repo.record_scrape_end.assert_called_once_with(21, "canceled")

    def test_abort_adapter_without_a_future_still_records_canceled(
        self, service, history_repo
    ):
        """An adapter never handed to the loop (``_run_future`` is None) is
        simply unregistered and recorded — no AttributeError."""
        adapter = self._adapter(22)
        adapter._run_future = None
        key = scraper_registry_key(False, "credit_cards", "max", "Card1")
        ss._active_scrapers[key] = adapter

        service.abort_scraping_process(22)

        assert key not in ss._active_scrapers
        history_repo.record_scrape_end.assert_called_once_with(22, "canceled")

    def test_abort_unknown_process_records_canceled(self, service, history_repo):
        """An id with no live adapter (already finished, or lost to a restart)
        still gets its row closed as CANCELED so the UI stops polling it."""
        service.abort_scraping_process(999)

        history_repo.record_scrape_end.assert_called_once_with(999, "canceled")
        assert ss._tfa_scrapers_waiting == {}


class TestScrapingServiceCustomPeriod:
    """Tests for custom scraping period date calculation."""

    def test_start_scraping_single_with_custom_period(
        self, service, launch, history_repo, create_adapter, is_2fa_required
    ):
        """Verify scraping_period_days overrides automatic start date calculation."""
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        history_repo.record_scrape_start.return_value = 42

        service.start_scraping_single(
            "banks", "hapoalim", "Main", scraping_period_days=30
        )

        expected_start = date.today() - timedelta(days=30)
        assert history_repo.record_scrape_start.call_args.args[3] == expected_start
        service.scraping_history_repo.get_last_successful_scrape_date.assert_not_called()


class TestScrapingServiceStartDate:
    """Tests for _get_scraper_start_date logic."""

    def test_get_scraper_start_date_with_iso_date(self, service):
        """Verify ISO format date string is parsed and 7-day buffer applied."""
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = (
            "2026-02-20T10:30:00"
        )

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        expected = datetime.fromisoformat("2026-02-20T10:30:00").date() - timedelta(days=7)
        assert result == expected

    def test_get_scraper_start_date_invalid_date_falls_back(self, service):
        """Verify invalid date string falls back to 365 days ago."""
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = (
            "not-a-date"
        )

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        assert result == date.today() - timedelta(days=365)

    def test_get_scraper_start_date_no_prior_scrape(self, service):
        """Verify None last scrape falls back to 365 days ago."""
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        result = service._get_scraper_start_date("banks", "hapoalim", "Main")

        assert result == date.today() - timedelta(days=365)

    def test_erased_history_yields_a_fresh_year_backfill(self, db_session):
        """Once an account's history rows are deleted (``delete_data=True``
        disconnect), the next start date is the fresh-account one-year window
        rather than the old watermark minus seven days."""
        from backend.repositories.scraping_history_repository import (
            ScrapingHistoryRepository,
        )

        history = ScrapingHistoryRepository(db_session)
        scrape_id = history.record_scrape_start(
            "banks", "hapoalim", "Main", date.today()
        )
        history.record_scrape_end(scrape_id, history.SUCCESS)
        real_service = ScrapingService(db_session)
        assert (
            date.today() - real_service._get_scraper_start_date("banks", "hapoalim", "Main")
        ).days == 7

        history.delete_for_account("banks", "hapoalim", "Main")

        start = real_service._get_scraper_start_date("banks", "hapoalim", "Main")
        assert (date.today() - start).days == 365
