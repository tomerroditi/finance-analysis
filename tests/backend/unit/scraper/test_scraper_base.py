"""Tests for scraper base classes, factory function, and 2FA requirement checks."""

import datetime

import pytest

from backend.scraper.scrapers import (
    DummyCreditCardScraper,
    DummyCreditCardTFAScraper,
    DummyRegularScraper,
    DummyTFAScraper,
    HapoalimScraper,
    IsracardScraper,
    get_scraper,
    is_2fa_required,
)


DUMMY_ACCOUNT = "test_account"
DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
DUMMY_START_DATE = datetime.date(2025, 1, 1)
DUMMY_PROCESS_ID = 42


class TestGetScraper:
    """Tests for the get_scraper factory function."""

    def test_get_credit_card_scraper(self):
        """Verify correct scraper type is returned for credit card providers."""
        scraper = get_scraper(
            "credit_cards",
            "isracard",
            DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS,
            DUMMY_START_DATE,
            DUMMY_PROCESS_ID,
        )
        assert isinstance(scraper, IsracardScraper)

    def test_get_bank_scraper(self):
        """Verify correct scraper type is returned for bank providers."""
        scraper = get_scraper(
            "banks",
            "hapoalim",
            DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS,
            DUMMY_START_DATE,
            DUMMY_PROCESS_ID,
        )
        assert isinstance(scraper, HapoalimScraper)

    def test_get_dummy_regular_scraper(self):
        """Verify DummyRegularScraper is returned for test_bank provider."""
        scraper = get_scraper(
            "banks",
            "test_bank",
            DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS,
            DUMMY_START_DATE,
            DUMMY_PROCESS_ID,
        )
        assert isinstance(scraper, DummyRegularScraper)

    def test_get_dummy_tfa_scraper(self):
        """Verify DummyTFAScraper is returned for test_bank_2fa provider."""
        scraper = get_scraper(
            "banks",
            "test_bank_2fa",
            DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS,
            DUMMY_START_DATE,
            DUMMY_PROCESS_ID,
        )
        assert isinstance(scraper, DummyTFAScraper)

    def test_get_scraper_unsupported_raises(self):
        """Verify ValueError is raised for unsupported service names."""
        with pytest.raises(ValueError, match="not supported"):
            get_scraper(
                "unsupported_service",
                "some_provider",
                DUMMY_ACCOUNT,
                DUMMY_CREDENTIALS,
                DUMMY_START_DATE,
                DUMMY_PROCESS_ID,
            )


class TestIs2FARequired:
    """Tests for the is_2fa_required helper function."""

    def test_onezero_requires_2fa(self):
        """Verify onezero bank provider requires 2FA."""
        assert is_2fa_required("banks", "onezero") is True

    def test_test_bank_no_2fa(self):
        """Verify test_bank provider does not require 2FA."""
        assert is_2fa_required("banks", "test_bank") is False

    def test_test_bank_2fa_requires_2fa(self):
        """Verify test_bank_2fa provider requires 2FA."""
        assert is_2fa_required("banks", "test_bank_2fa") is True


class TestScraperBaseAttributes:
    """Tests for the Scraper base class attributes and methods."""

    def test_scraper_init(self):
        """Verify scraper initializes with correct account_name, credentials, and process_id."""
        scraper = DummyRegularScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.account_name == DUMMY_ACCOUNT
        assert scraper.credentials == DUMMY_CREDENTIALS
        assert scraper.process_id == DUMMY_PROCESS_ID

    def test_scraper_cancel_constant(self):
        """Verify the CANCEL constant is set to 'cancel'."""
        scraper = DummyRegularScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.CANCEL == "cancel"

    def test_set_otp_code(self):
        """Verify set_otp_code sets the code and signals the OTP event."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert not scraper.otp_event.is_set()
        scraper.set_otp_code("123456")
        assert scraper.otp_code == "123456"
        assert scraper.otp_event.is_set()

    def test_is_waiting_for_otp(self):
        """Verify is_waiting_for_otp returns True when code is 'waiting for input'."""
        scraper = DummyTFAScraper(
            DUMMY_ACCOUNT, DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID
        )
        assert scraper.is_waiting_for_otp is False
        scraper.otp_code = "waiting for input"
        assert scraper.is_waiting_for_otp is True
