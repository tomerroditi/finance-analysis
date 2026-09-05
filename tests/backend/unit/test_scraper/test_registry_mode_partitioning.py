"""Tests that the scraper registries are partitioned by demo mode.

Demo Mode is per-client: two clients on one backend can be in opposite
modes at the same time. The module-level scraper registries
(``_active_scrapers``, ``_tfa_scrapers_waiting``) and the abort path's
``process_id`` matching predate that and carry no mode, so a demo client
and a real client could collide on:

* the same ``"{service} - {provider} - {account}"`` account key — demo
  seed credentials use names like ``"Main Account"`` and ``"Family Card"``,
  which a real user can plausibly reuse; and
* the same ``process_id`` — it is a per-database autoincrement, so demo
  ``5`` and real ``5`` are different scrapes.

No wrong-mode data is written either way (each adapter captures its own
mode at construction and re-applies it in ``run()``), but the collisions
produce cross-client status confusion and cross-client aborts.
"""

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import backend.services.scraping_service as ss
from backend.config import AppConfig
from backend.scraper.adapter import (
    ScraperAdapter,
    _active_scrapers,
    _tfa_scrapers_waiting,
    scraper_registry_key,
)
from backend.services.scraping_service import ScrapingService

DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
DUMMY_START_DATE = date(2025, 1, 1)


@pytest.fixture(autouse=True)
def reset_registries():
    """Clear both module-level registries so tests never leak state."""
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()
    yield
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()


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


@contextmanager
def demo_mode(enabled: bool):
    """Run the block with the demo flag pinned, restoring it afterwards."""
    config = AppConfig()
    token = config.set_demo_mode(enabled)
    try:
        yield
    finally:
        config.reset_demo_mode(token)


def _adapter(process_id: int, demo: bool) -> ScraperAdapter:
    """Build an adapter that captured ``demo`` as its mode at construction."""
    with demo_mode(demo):
        return ScraperAdapter(
            "credit_cards", "isracard", "Family Card",
            DUMMY_CREDENTIALS, DUMMY_START_DATE, process_id,
        )


class TestRegistryKeyCarriesMode:
    """The registry key must distinguish otherwise-identical accounts."""

    def test_same_account_differs_by_mode(self):
        """Verify one account name yields different keys per mode."""
        real = scraper_registry_key(False, "banks", "hapoalim", "Main Account")
        demo = scraper_registry_key(True, "banks", "hapoalim", "Main Account")
        assert real != demo

    def test_same_mode_and_account_is_stable(self):
        """Verify the key is deterministic for a given mode and account."""
        first = scraper_registry_key(True, "banks", "hapoalim", "Main Account")
        second = scraper_registry_key(True, "banks", "hapoalim", "Main Account")
        assert first == second

    def test_account_names_containing_the_old_delimiter_do_not_collide(self):
        """Verify a literal ' - ' in an account name cannot forge another key.

        The previous key was the interpolated string
        ``f"{service} - {provider} - {account}"``, so a user-supplied
        account name containing the delimiter could in principle land on
        another account's key.
        """
        a = scraper_registry_key(False, "banks", "hapoalim", "A - B")
        b = scraper_registry_key(False, "banks", "hapoalim - A", "B")
        assert a != b


class TestRegistriesTrackModesIndependently:
    """Two adapters for one account in opposite modes must coexist."""

    def test_active_scrapers_holds_both_modes(self):
        """Verify registering a demo adapter does not evict the real one."""
        real_adapter = _adapter(process_id=5, demo=False)
        demo_adapter = _adapter(process_id=5, demo=True)

        real_key = scraper_registry_key(
            False, "credit_cards", "isracard", "Family Card"
        )
        demo_key = scraper_registry_key(
            True, "credit_cards", "isracard", "Family Card"
        )
        _active_scrapers[real_key] = real_adapter
        _active_scrapers[demo_key] = demo_adapter

        assert _active_scrapers[real_key] is real_adapter
        assert _active_scrapers[demo_key] is demo_adapter

    def test_unregister_pops_only_its_own_mode(self):
        """Verify an adapter's cleanup leaves the other mode's entry intact.

        ``run()``'s finally block calls this; before partitioning it popped
        the single shared key and would have released the other client's
        single-flight lock.
        """
        real_adapter = _adapter(process_id=5, demo=False)
        demo_adapter = _adapter(process_id=5, demo=True)

        real_key = scraper_registry_key(
            False, "credit_cards", "isracard", "Family Card"
        )
        demo_key = scraper_registry_key(
            True, "credit_cards", "isracard", "Family Card"
        )
        _active_scrapers[real_key] = real_adapter
        _active_scrapers[demo_key] = demo_adapter
        _tfa_scrapers_waiting[real_key] = real_adapter
        _tfa_scrapers_waiting[demo_key] = demo_adapter

        demo_adapter._unregister_from_2fa_waiting()

        assert demo_key not in _active_scrapers
        assert demo_key not in _tfa_scrapers_waiting
        assert _active_scrapers[real_key] is real_adapter
        assert _tfa_scrapers_waiting[real_key] is real_adapter


class TestSingleFlightCheckIsModeScoped:
    """The single-flight guard must not see the other mode's run."""

    @patch("backend.services.scraping_service.asyncio")
    @patch("backend.services.scraping_service.create_adapter")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_demo_start_ignores_a_real_run_for_the_same_account(
        self, mock_is_2fa, mock_get_db_ctx, mock_create_adapter, mock_asyncio, service
    ):
        """Verify a demo client launches its own scrape and gets its own id.

        Before partitioning, the demo client received the REAL run's
        ``process_id`` with no scrape launched, then polled its own
        database for an id that meant something else there.
        """
        real_adapter = MagicMock()
        real_adapter.process_id = 5
        _active_scrapers[
            scraper_registry_key(False, "credit_cards", "isracard", "Family Card")
        ] = real_adapter

        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 99

        demo_adapter = mock_create_adapter.return_value
        demo_adapter.process_id = 99

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ), demo_mode(True):
            returned = service.start_scraping_single(
                "credit_cards", "isracard", "Family Card"
            )

        assert returned == 99
        mock_create_adapter.assert_called_once()
        assert (
            _active_scrapers[
                scraper_registry_key(True, "credit_cards", "isracard", "Family Card")
            ]
            is demo_adapter
        )


class TestAbortIsModeScoped:
    """An abort must not reach across the mode boundary."""

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_leaves_the_other_modes_scraper_running(
        self, mock_get_db_ctx, service
    ):
        """Verify aborting demo process 5 does not cancel real process 5."""
        real_adapter = MagicMock()
        real_adapter.process_id = 5
        real_adapter.demo_mode = False
        demo_adapter = MagicMock()
        demo_adapter.process_id = 5
        demo_adapter.demo_mode = True

        real_key = scraper_registry_key(
            False, "credit_cards", "isracard", "Family Card"
        )
        demo_key = scraper_registry_key(
            True, "credit_cards", "isracard", "Family Card"
        )
        _tfa_scrapers_waiting[real_key] = real_adapter
        _tfa_scrapers_waiting[demo_key] = demo_adapter
        _active_scrapers[real_key] = real_adapter
        _active_scrapers[demo_key] = demo_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ), demo_mode(True):
            service.abort_scraping_process(5)

        demo_adapter.set_otp_code.assert_called_once_with(ScraperAdapter.CANCEL)
        real_adapter.set_otp_code.assert_not_called()
        assert demo_key not in _tfa_scrapers_waiting
        assert demo_key not in _active_scrapers
        assert _tfa_scrapers_waiting[real_key] is real_adapter
        assert _active_scrapers[real_key] is real_adapter

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_still_cancels_its_own_modes_scraper(
        self, mock_get_db_ctx, service
    ):
        """Verify the mode check did not break aborting the right scraper."""
        demo_adapter = MagicMock()
        demo_adapter.process_id = 7
        demo_adapter.demo_mode = True
        demo_key = scraper_registry_key(True, "banks", "leumi", "Main Account")
        _tfa_scrapers_waiting[demo_key] = demo_adapter
        _active_scrapers[demo_key] = demo_adapter

        mock_history_repo = MagicMock()
        mock_history_repo.FAILED = "failed"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ), demo_mode(True):
            service.abort_scraping_process(7)

        demo_adapter.set_otp_code.assert_called_once_with(ScraperAdapter.CANCEL)
        mock_history_repo.record_scrape_end.assert_called_once_with(7, "failed")
        assert demo_key not in _tfa_scrapers_waiting
        assert demo_key not in _active_scrapers


class TestTwoFactorSubmitIsModeScoped:
    """Submitting an OTP must resolve the caller's own adapter."""

    def test_demo_submit_does_not_reach_the_real_adapter(self, service):
        """Verify an OTP submitted in demo mode goes to the demo adapter."""
        real_adapter = MagicMock()
        demo_adapter = MagicMock()
        _tfa_scrapers_waiting[
            scraper_registry_key(False, "credit_cards", "isracard", "Family Card")
        ] = real_adapter
        _tfa_scrapers_waiting[
            scraper_registry_key(True, "credit_cards", "isracard", "Family Card")
        ] = demo_adapter

        with demo_mode(True):
            service.submit_2fa_code(
                "credit_cards", "isracard", "Family Card", "123456"
            )

        demo_adapter.set_otp_code.assert_called_once_with("123456")
        real_adapter.set_otp_code.assert_not_called()
