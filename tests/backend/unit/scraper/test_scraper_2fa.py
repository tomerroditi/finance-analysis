"""Tests for scraper 2FA (Two-Factor Authentication) functionality."""

import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

from backend.scraper.scrapers import (
    DummyRegularScraper,
    DummyTFAScraper,
    HapoalimScraper,
)


DUMMY_ACCOUNT = "test_account"
DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
HAPOALIM_CREDENTIALS = {"userCode": "test_user", "password": "test_pass"}
DUMMY_START_DATE = datetime.date(2025, 1, 1)
DUMMY_PROCESS_ID = 42


class TestScraper2FA:
    """Tests for 2FA-related scraper attributes and methods."""

    def test_otp_event_initially_unset(self):
        """Verify that the OTP event starts in an unset state."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert not scraper.otp_event.is_set()

    def test_set_otp_code_sets_event(self):
        """Verify that set_otp_code triggers the OTP event."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.set_otp_code("123456")
        assert scraper.otp_event.is_set()

    def test_set_otp_code_stores_code(self):
        """Verify that the OTP code is stored on the scraper instance."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.set_otp_code("789012")
        assert scraper.otp_code == "789012"

    def test_cancel_sets_cancel_constant(self):
        """Verify that setting 'cancel' as OTP code triggers cancellation."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.set_otp_code("cancel")
        assert scraper.otp_code == scraper.CANCEL

    def test_is_waiting_for_otp_true(self):
        """Verify waiting state is detected when code is 'waiting for input'."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.otp_code = "waiting for input"
        assert scraper.is_waiting_for_otp is True

    def test_is_waiting_for_otp_false(self):
        """Verify not-waiting state after an actual OTP code is set."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.set_otp_code("123456")
        assert scraper.is_waiting_for_otp is False

    def test_requires_2fa_attribute(self):
        """Verify requires_2fa is True for 2FA scrapers like DummyTFAScraper."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.requires_2fa is True

    def test_requires_2fa_false_for_regular(self):
        """Verify requires_2fa is False for regular scrapers like DummyRegularScraper."""
        scraper = DummyRegularScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.requires_2fa is False


def _make_mock_process(stdout_lines, stderr_output="", return_code=0):
    """Create a mock subprocess.Popen process with the given stdout lines.

    Parameters
    ----------
    stdout_lines : list[str]
        Lines to yield from stdout.readline(), with a final empty string
        to signal EOF.
    stderr_output : str
        Content returned by stderr.read().
    return_code : int
        Return code from process.poll() after stdout is exhausted.
    """
    mock_process = MagicMock()

    call_count = 0
    lines = list(stdout_lines) + [""]

    def readline_side_effect():
        nonlocal call_count
        if call_count < len(lines):
            line = lines[call_count]
            call_count += 1
            return line
        return ""

    mock_process.stdout.readline = readline_side_effect

    # poll returns None while there are lines to read, then the return code
    def poll_side_effect():
        if call_count < len(lines):
            return None
        return return_code

    mock_process.poll = poll_side_effect

    mock_process.stdout.read.return_value = ""
    mock_process.stderr.read.return_value = stderr_output
    mock_process.wait.return_value = return_code
    return mock_process


class TestHapoalimScraper2FADetection:
    """Tests for HapoalimScraper's automatic 2FA detection from Node.js output."""

    @patch("backend.scraper.scrapers.get_db_context")
    @patch("backend.scraper.scrapers.subprocess.Popen")
    def test_detects_2fa_from_stdout(self, mock_popen, mock_db_ctx):
        """Verify that '2FA page detected' in stdout sets tfa_detected flag."""
        mock_process = _make_mock_process(
            stdout_lines=[
                "2FA page detected\n",
                "writing scraped data to console\n",
            ],
        )
        mock_popen.return_value = mock_process

        # Mock the DB context manager used inside scrape_data
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.scrape_data("2025-01-01")

        assert scraper.tfa_detected is True

    @patch("backend.scraper.scrapers.get_db_context")
    @patch("backend.scraper.scrapers.subprocess.Popen")
    def test_no_2fa_when_success_without_signal(self, mock_popen, mock_db_ctx):
        """Verify tfa_detected is False when scraping succeeds without 2FA."""
        mock_process = _make_mock_process(
            stdout_lines=[
                "writing scraped data to console\n",
            ],
        )
        mock_popen.return_value = mock_process

        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.scrape_data("2025-01-01")

        assert scraper.tfa_detected is False

    @patch("backend.scraper.scrapers.get_db_context")
    @patch("backend.scraper.scrapers.subprocess.Popen")
    def test_2fa_updates_scraping_history_status(self, mock_popen, mock_db_ctx):
        """Verify that 2FA detection updates the scraping history to WAITING_FOR_2FA."""
        mock_process = _make_mock_process(
            stdout_lines=[
                "2FA page detected\n",
                "writing scraped data to console\n",
            ],
        )
        mock_popen.return_value = mock_process

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        scraper.scrape_data("2025-01-01")

        # Verify that record_scrape_end was called with WAITING_FOR_2FA
        from backend.repositories.scraping_history_repository import (
            ScrapingHistoryRepository,
        )

        mock_db_ctx.assert_called()

    @patch("backend.scraper.scrapers.subprocess.Popen")
    def test_tfa_required_error_from_stderr(self, mock_popen):
        """Verify that TFA_REQUIRED error from Node.js stderr raises TwoFactorAuthRequiredError."""
        mock_process = _make_mock_process(
            stdout_lines=[],
            stderr_output="logging error: TFA_REQUIRED: 2FA verification was not completed in time.",
        )
        mock_popen.return_value = mock_process

        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )

        from backend.scraper.exceptions import TwoFactorAuthRequiredError

        try:
            scraper.scrape_data("2025-01-01")
        except TwoFactorAuthRequiredError:
            pass  # Expected
        else:
            assert scraper.error != "", "Should have set error for TFA_REQUIRED"

    @patch("backend.scraper.scrapers.subprocess.Popen")
    def test_non_2fa_timeout_not_detected_as_2fa(self, mock_popen):
        """Verify that a generic TIMEOUT error from Node.js is NOT treated as 2FA."""
        mock_process = _make_mock_process(
            stdout_lines=[],
            stderr_output="logging error: TIMEOUT: Operation timed out",
        )
        mock_popen.return_value = mock_process

        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )

        from backend.scraper.exceptions import TimeoutError

        try:
            scraper.scrape_data("2025-01-01")
        except TimeoutError:
            pass  # Expected — should be a timeout, not 2FA
        assert scraper.tfa_detected is False

    def test_hapoalim_scraper_provider_name(self):
        """Verify HapoalimScraper has correct provider_name."""
        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.provider_name == "hapoalim"

    def test_hapoalim_scraper_service_name(self):
        """Verify HapoalimScraper has correct service_name."""
        scraper = HapoalimScraper(
            DUMMY_ACCOUNT, HAPOALIM_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.service_name == "banks"
