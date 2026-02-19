"""Tests for scraper 2FA (Two-Factor Authentication) functionality."""

import datetime

from backend.scraper.scrapers import (
    DummyRegularScraper,
    DummyTFAScraper,
)


DUMMY_ACCOUNT = "test_account"
DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
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
