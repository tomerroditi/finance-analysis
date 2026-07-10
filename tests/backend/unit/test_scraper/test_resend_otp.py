"""Tests for the scraper-layer ``resend_otp`` in-place OTP re-issue.

Covers the base-class default (``ResendNotSupportedError``), the OneZero
override (re-runs prepare, updates ``_otp_context``, is rate-limited), and
the dummy 2FA scraper's no-op resend used by demo-mode e2e.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from scraper.base.base_scraper import ResendNotSupportedError, ScraperOptions
from scraper.providers.banks import onezero
from scraper.providers.banks.onezero import IDENTITY_SERVER_URL, OneZeroScraper
from scraper.providers.test.dummy_tfa import DummyTFAScraper
from scraper.utils.otp_rate_limit import OtpRateLimitError, otp_prepare_rate_limiter


@pytest.fixture(autouse=True)
def reset_otp_rate_limiter():
    """Reset the shared rate limiter so tests never leak state between runs."""
    otp_prepare_rate_limiter.reset()
    yield
    otp_prepare_rate_limiter.reset()


class TestBaseScraperResendNotSupported:
    """The base scraper refuses in-place resend by default."""

    def test_base_resend_raises_not_supported(self):
        """A provider that doesn't override resend_otp raises ResendNotSupportedError."""

        # DummyRegularScraper subclasses BaseScraper without overriding resend.
        from scraper.providers.test.dummy_regular import DummyRegularScraper

        scraper = DummyRegularScraper(
            provider="test_bank",
            credentials={"email": "e", "password": "p"},
            options=ScraperOptions(),
        )

        with pytest.raises(ResendNotSupportedError):
            asyncio.run(scraper.resend_otp())


class TestOneZeroResendOtp:
    """OneZero re-issues the SMS in place by re-running prepare."""

    def _make_scraper(self) -> OneZeroScraper:
        """Build a OneZeroScraper with a phone number and a stub client."""
        scraper = OneZeroScraper(
            provider="onezero",
            credentials={
                "email": "test@test.com",
                "password": "pass",
                "phoneNumber": "+15551234567",
            },
            options=ScraperOptions(),
        )
        scraper.client = None  # fetch_post is mocked, so no real client needed
        return scraper

    def test_resend_reissues_prepare_and_updates_context(self):
        """resend_otp re-runs prepare and refreshes _otp_context to the new value."""
        scraper = self._make_scraper()
        scraper._otp_context = "old-ctx"

        device_ok = {"resultData": {"deviceToken": "dt"}}
        prepare_ok = {"resultData": {"otpContext": "new-ctx"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(side_effect=[device_ok, prepare_ok]),
            ) as mock_post:
                await scraper.resend_otp()
                return mock_post.call_args_list

        calls = asyncio.run(run())

        assert scraper._otp_context == "new-ctx"
        prepare_calls = [
            c for c in calls if IDENTITY_SERVER_URL + "/otp/prepare" in c.args
        ]
        assert len(prepare_calls) == 1

    def test_resend_is_rate_limited(self):
        """A blocked limiter makes resend_otp raise OtpRateLimitError (no SMS)."""
        scraper = self._make_scraper()
        device_ok = {"resultData": {"deviceToken": "dt"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(return_value=device_ok),
            ) as mock_post, patch.object(
                onezero.otp_prepare_rate_limiter,
                "check_and_record",
                side_effect=OtpRateLimitError("Wait about a minute"),
            ):
                with pytest.raises(OtpRateLimitError, match="Wait about a minute"):
                    await scraper.resend_otp()
                return mock_post.call_args_list

        calls = asyncio.run(run())
        prepare_calls = [
            c for c in calls if IDENTITY_SERVER_URL + "/otp/prepare" in c.args
        ]
        assert prepare_calls == []

    def test_resend_does_not_touch_otp_event_or_code(self):
        """resend_otp only mutates _otp_context — it never sets the OTP event/code.

        The scraper coroutine is parked in the adapter's _otp_callback on
        ``_otp_event``; a resend must not wake it or plant a code, or the
        user's freshly requested SMS would be verified against a stale
        context.
        """
        scraper = self._make_scraper()
        device_ok = {"resultData": {"deviceToken": "dt"}}
        prepare_ok = {"resultData": {"otpContext": "new-ctx"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(side_effect=[device_ok, prepare_ok]),
            ):
                await scraper.resend_otp()

        asyncio.run(run())
        # OneZeroScraper has no _otp_event/_otp_code of its own — those live
        # on the adapter. Assert resend didn't accidentally introduce them.
        assert not hasattr(scraper, "_otp_event")
        assert not hasattr(scraper, "_otp_code")


class TestDummyTFAResendOtp:
    """The dummy 2FA scraper supports resend so demo-mode e2e can exercise it."""

    def test_dummy_resend_is_noop(self):
        """DummyTFAScraper.resend_otp completes without raising (no-op)."""
        scraper = DummyTFAScraper(
            provider="test_bank_2fa",
            credentials={"email": "e", "password": "p"},
            options=ScraperOptions(),
        )
        # Must not raise ResendNotSupportedError like the base class would.
        asyncio.run(scraper.resend_otp())
