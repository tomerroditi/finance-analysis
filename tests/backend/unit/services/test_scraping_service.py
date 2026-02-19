"""Tests for ScrapingService."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
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
        """Verify get_scraping_status returns dict with status, process_id, and error_message."""
        service.scraping_history_repo.get_scraping_status.return_value = "in_progress"
        service.scraping_history_repo.get_error_message.return_value = None

        result = service.get_scraping_status(42)

        assert result == {
            "status": "in_progress",
            "process_id": 42,
            "error_message": None,
        }
        service.scraping_history_repo.get_scraping_status.assert_called_once_with(42)
        service.scraping_history_repo.get_error_message.assert_called_once_with(42)

    def test_get_scraping_status_unknown(self, service):
        """Verify status is 'unknown' when repository returns None."""
        service.scraping_history_repo.get_scraping_status.return_value = None
        service.scraping_history_repo.get_error_message.return_value = None

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

    @patch("backend.services.scraping_service.Thread")
    @patch("backend.services.scraping_service.get_scraper")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_single(
        self, mock_is_2fa, mock_get_db_ctx, mock_get_scraper, mock_thread, service
    ):
        """Verify start_scraping_single returns a process_id and starts a thread."""
        mock_is_2fa.return_value = False
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 7

        mock_inner_db = MagicMock()

        @contextmanager
        def fake_db_context():
            yield mock_inner_db

        mock_get_db_ctx.side_effect = fake_db_context

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            process_id = service.start_scraping_single("banks", "hapoalim", "Main")

        assert process_id == 7
        mock_thread.return_value.start.assert_called_once()

    @patch("backend.services.scraping_service.Thread")
    @patch("backend.services.scraping_service.get_scraper")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_creates_history(
        self, mock_is_2fa, mock_get_db_ctx, mock_get_scraper, mock_thread, service
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

    @patch("backend.services.scraping_service.Thread")
    @patch("backend.services.scraping_service.get_scraper")
    @patch("backend.services.scraping_service.get_db_context")
    @patch("backend.services.scraping_service.is_2fa_required")
    def test_start_scraping_2fa_adds_to_waiting(
        self, mock_is_2fa, mock_get_db_ctx, mock_get_scraper, mock_thread, service
    ):
        """Verify scraper is added to _tfa_scrapers_waiting when 2FA is required."""
        mock_is_2fa.return_value = True
        service.credentials_repo.get_credentials.return_value = {"user": "test"}
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        mock_history_repo = MagicMock()
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"
        mock_history_repo.record_scrape_start.return_value = 15

        mock_scraper = MagicMock()
        mock_get_scraper.return_value = mock_scraper

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
        assert ss._tfa_scrapers_waiting[expected_key][0] is mock_scraper


class TestScrapingService2FA:
    """Tests for 2FA code submission."""

    def test_submit_2fa_code(self, service):
        """Verify set_otp_code is called on the correct scraper."""
        mock_scraper = MagicMock()
        mock_thread = MagicMock()
        name = "credit_cards - isracard - Main"
        ss._tfa_scrapers_waiting[name] = (mock_scraper, mock_thread)

        service.submit_2fa_code("credit_cards", "isracard", "Main", "123456")

        mock_scraper.set_otp_code.assert_called_once_with("123456")

    def test_submit_2fa_code_not_found(self, service):
        """Verify EntityNotFoundException raised for unknown scraper."""
        with pytest.raises(EntityNotFoundException):
            service.submit_2fa_code("banks", "unknown", "NoAccount", "000000")


class TestScrapingServiceAbort:
    """Tests for aborting scraping processes."""

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_scraping_process(self, mock_get_db_ctx, service):
        """Verify CANCEL is sent and history is recorded as failed."""
        mock_scraper = MagicMock()
        mock_scraper.process_id = 20
        mock_scraper.CANCEL = "cancel"
        mock_thread = MagicMock()
        ss._tfa_scrapers_waiting["banks - leumi - Acc"] = (mock_scraper, mock_thread)

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

        mock_scraper.set_otp_code.assert_called_once_with("cancel")
        mock_history_repo.record_scrape_end.assert_called_once_with(20, "failed")
        assert "banks - leumi - Acc" not in ss._tfa_scrapers_waiting

    @patch("backend.services.scraping_service.get_db_context")
    def test_abort_2fa_scraper(self, mock_get_db_ctx, service):
        """Verify CANCEL is sent to 2FA scraper via set_otp_code."""
        mock_scraper = MagicMock()
        mock_scraper.process_id = 55
        mock_scraper.CANCEL = "cancel"
        mock_thread = MagicMock()
        ss._tfa_scrapers_waiting["credit_cards - max - Card1"] = (
            mock_scraper,
            mock_thread,
        )

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

        mock_scraper.set_otp_code.assert_called_once_with("cancel")
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
