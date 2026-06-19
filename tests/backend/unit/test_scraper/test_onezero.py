"""Tests for the OneZero bank scraper identity-server URLs and OTP retry logic."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
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


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Construct an ``httpx.HTTPStatusError`` carrying the given status code."""
    url = f"{IDENTITY_SERVER_URL}/otp/prepare"
    request = httpx.Request("POST", url)
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"status {status_code}", request=request, response=response
    )


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


class TestPostWithRetry:
    """Tests for the transient-failure retry helper on the OneZero scraper."""

    def test_retries_on_503_then_succeeds(self):
        """A 503 retries with backoff and ultimately returns the success payload."""
        scraper = _make_scraper()
        success = {"resultData": {"otpContext": "ctx"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(
                    side_effect=[
                        _http_status_error(503),
                        _http_status_error(503),
                        success,
                    ]
                ),
            ) as mock_post, patch.object(
                onezero.asyncio, "sleep", new=AsyncMock()
            ) as mock_sleep:
                result = await scraper._post_with_retry(
                    f"{IDENTITY_SERVER_URL}/otp/prepare", {"foo": "bar"}
                )
                return result, mock_post.call_count, mock_sleep.call_count

        result, post_calls, sleep_calls = asyncio.run(run())
        assert result == success
        assert post_calls == 3
        assert sleep_calls == 2

    def test_does_not_retry_on_401(self):
        """A 401 (auth failure) is not transient and is re-raised immediately."""
        scraper = _make_scraper()

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(side_effect=_http_status_error(401)),
            ) as mock_post, patch.object(
                onezero.asyncio, "sleep", new=AsyncMock()
            ) as mock_sleep:
                with pytest.raises(httpx.HTTPStatusError):
                    await scraper._post_with_retry(
                        f"{IDENTITY_SERVER_URL}/otp/verify", {"foo": "bar"}
                    )
                return mock_post.call_count, mock_sleep.call_count

        post_calls, sleep_calls = asyncio.run(run())
        assert post_calls == 1
        assert sleep_calls == 0

    def test_retries_on_transport_error(self):
        """A transport-level error (ConnectError) is retried like a 5xx."""
        scraper = _make_scraper()
        success = {"resultData": {"deviceToken": "dt"}}

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(
                    side_effect=[
                        httpx.ConnectError("boom"),
                        success,
                    ]
                ),
            ) as mock_post, patch.object(
                onezero.asyncio, "sleep", new=AsyncMock()
            ) as mock_sleep:
                result = await scraper._post_with_retry(
                    f"{IDENTITY_SERVER_URL}/devices/token", {"foo": "bar"}
                )
                return result, mock_post.call_count, mock_sleep.call_count

        result, post_calls, sleep_calls = asyncio.run(run())
        assert result == success
        assert post_calls == 2
        assert sleep_calls == 1

    def test_exhausts_attempts_and_reraises(self):
        """When every attempt is transient, the last error is re-raised."""
        scraper = _make_scraper()

        async def run():
            with patch.object(
                onezero,
                "fetch_post",
                new=AsyncMock(side_effect=_http_status_error(503)),
            ) as mock_post, patch.object(
                onezero.asyncio, "sleep", new=AsyncMock()
            ) as mock_sleep:
                with pytest.raises(httpx.HTTPStatusError):
                    await scraper._post_with_retry(
                        f"{IDENTITY_SERVER_URL}/otp/prepare", {"foo": "bar"}
                    )
                return mock_post.call_count, mock_sleep.call_count

        post_calls, sleep_calls = asyncio.run(run())
        assert post_calls == onezero.OTP_PREPARE_RETRY_ATTEMPTS
        assert sleep_calls == onezero.OTP_PREPARE_RETRY_ATTEMPTS - 1


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
