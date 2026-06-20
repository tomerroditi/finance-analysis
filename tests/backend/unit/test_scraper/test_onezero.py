"""Tests for the OneZero bank scraper: identity-server URLs, OTP flow, errors."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from scraper.base.base_scraper import ScraperOptions
from scraper.providers.banks import onezero
from scraper.providers.banks.onezero import IDENTITY_SERVER_URL, OneZeroScraper


class TestRefreshedOtpToken:
    """The scraper exposes a long-term token only when it obtains a fresh one."""

    def test_interactive_flow_records_fresh_token(self):
        """No stored token → interactive flow sets refreshed_otp_long_term_token."""
        scraper = OneZeroScraper(
            provider="onezero",
            credentials={"email": "e", "password": "p", "phoneNumber": "+15551234567"},
            options=ScraperOptions(),
        )
        scraper.on_otp_request = AsyncMock(return_value="123456")

        async def run():
            with patch.object(
                scraper, "_trigger_two_factor_auth",
                new=AsyncMock(return_value={"success": True}),
            ), patch.object(
                scraper, "_get_long_term_token",
                new=AsyncMock(return_value={"success": True, "long_term_token": "NEWTOKEN"}),
            ):
                return await scraper._resolve_otp_token()

        token = asyncio.run(run())
        assert token == "NEWTOKEN"
        assert scraper.refreshed_otp_long_term_token == "NEWTOKEN"

    def test_stored_token_leaves_refreshed_none(self):
        """A stored token is reused and no fresh token is recorded."""
        scraper = OneZeroScraper(
            provider="onezero",
            credentials={"email": "e", "password": "p", "otpLongTermToken": "STORED"},
            options=ScraperOptions(),
        )
        token = asyncio.run(scraper._resolve_otp_token())
        assert token == "STORED"
        assert scraper.refreshed_otp_long_term_token is None


def _make_scraper() -> OneZeroScraper:
    """Build a OneZeroScraper instance suitable for fully-mocked unit tests."""
    scraper = OneZeroScraper(
        provider="onezero",
        credentials={"email": "test@test.com", "password": "pass"},
        options=ScraperOptions(),
    )
    scraper.client = None  # fetch_post is mocked, so no real client is needed
    return scraper


class TestIdentityServerUrl:
    """Tests for the identity-server URL construction."""

    def test_identity_server_url_has_no_trailing_slash(self):
        """The base URL must not end with '/' so built paths get a single slash."""
        assert not IDENTITY_SERVER_URL.endswith("/")

    def test_built_url_has_single_slash(self):
        """A built endpoint URL must contain '/v1/otp/verify', never '/v1//otp'."""
        built = f"{IDENTITY_SERVER_URL}/otp/verify"
        assert "/v1/otp/verify" in built
        assert "/v1//otp" not in built


class TestPrepareNotRetried:
    """The OTP-prepare flow makes a single attempt — no retries.

    Retrying /otp/prepare fires repeated SMS-send requests, which trips the
    provider's fraud detection (Twilio temporarily blocks the number prefix).
    A failure must therefore propagate after exactly one prepare call.
    """

    def test_prepare_failure_is_not_retried(self):
        """A failure on /otp/prepare propagates after one prepare call (no retry)."""
        scraper = _make_scraper()
        device_ok = {"resultData": {"deviceToken": "dt"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(side_effect=[device_ok, Exception("503 prefix blocked")]),
            ) as mock_post:
                with pytest.raises(Exception, match="prefix blocked"):
                    await scraper._trigger_two_factor_auth("+15551234567")
                return mock_post.call_count

        # devices/token (1) + otp/prepare (1) = 2 calls, no retries.
        assert asyncio.run(run()) == 2


class TestLoginErrorDetail:
    """login() records the failure detail so the UI can show the real reason."""

    def test_resolve_failure_records_detail_and_returns_unknown(self):
        """When OTP resolution raises, login stores the message and reports UNKNOWN_ERROR."""
        scraper = _make_scraper()

        async def run():
            with patch.object(
                scraper,
                "_resolve_otp_token",
                new=AsyncMock(
                    side_effect=Exception(
                        "HTTP 503 /v1/otp/prepare — body: prefix blocked"
                    )
                ),
            ):
                return await scraper.login()

        result = asyncio.run(run())
        assert result is onezero.LoginResult.UNKNOWN_ERROR
        assert "prefix blocked" in scraper._login_error_detail
