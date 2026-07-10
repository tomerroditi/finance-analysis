"""Tests for ScrapingService.resend_2fa_code (in-place OTP resend + fallback).

The service resolves the active adapter and asks it to re-issue the OTP in
place. For providers that support it (OneZero) the same process stays alive
(``status: resent``); for providers that don't (browser-based, raising
``ResendNotSupportedError``) it falls back to abort + relaunch
(``status: restarted``). A rate-limit violation surfaces as
``BadRequestException`` (HTTP 400).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.scraping_service as ss
from backend.errors import BadRequestException, EntityNotFoundException
from backend.scraper.adapter import OtpRateLimitError, ResendNotSupportedError
from backend.services.scraping_service import ScrapingService


@pytest.fixture(autouse=True)
def reset_registries():
    """Clear both module-level registries between tests."""
    ss._tfa_scrapers_waiting.clear()
    ss._active_scrapers.clear()
    yield
    ss._tfa_scrapers_waiting.clear()
    ss._active_scrapers.clear()


@pytest.fixture(autouse=True)
def reset_credentials_singleton():
    """Reset the CredentialsRepository singleton between tests."""
    from backend.repositories.credentials_repository import CredentialsRepository

    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False
    yield
    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False


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


class TestResend2FACodeSuccess:
    """A resend-capable adapter re-issues in place — no abort/restart."""

    def test_resent_returns_status_and_same_process_id(self, service):
        """Active OneZero adapter → resend_otp called, status 'resent', same pid."""
        adapter = MagicMock()
        adapter.process_id = 77
        adapter.resend_otp = AsyncMock()
        ss._active_scrapers["banks - onezero - Acc"] = adapter

        with patch.object(service, "abort_scraping_process") as abort, patch.object(
            service, "start_scraping_single"
        ) as start:
            result = asyncio.run(
                service.resend_2fa_code("banks", "onezero", "Acc")
            )

        adapter.resend_otp.assert_awaited_once_with()
        assert result == {"status": "resent", "process_id": 77}
        # In-place resend must NOT abort or relaunch.
        abort.assert_not_called()
        start.assert_not_called()

    def test_falls_back_to_tfa_waiting_registry(self, service):
        """When absent from _active_scrapers, the adapter is found in _tfa_scrapers_waiting."""
        adapter = MagicMock()
        adapter.process_id = 88
        adapter.resend_otp = AsyncMock()
        ss._tfa_scrapers_waiting["banks - onezero - Acc"] = adapter

        result = asyncio.run(service.resend_2fa_code("banks", "onezero", "Acc"))

        adapter.resend_otp.assert_awaited_once_with()
        assert result == {"status": "resent", "process_id": 88}


class TestResend2FACodeNotFound:
    """No waiting/active adapter → EntityNotFoundException (route 404)."""

    def test_no_adapter_raises_not_found(self, service):
        """resend_2fa_code raises EntityNotFoundException when nothing is registered."""
        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.resend_2fa_code("banks", "onezero", "Missing"))


class TestResend2FACodeRateLimited:
    """A rate-limit violation is mapped to BadRequestException (route 400)."""

    def test_rate_limit_maps_to_bad_request(self, service):
        """OtpRateLimitError from the adapter surfaces as BadRequestException."""
        adapter = MagicMock()
        adapter.process_id = 90
        adapter.resend_otp = AsyncMock(
            side_effect=OtpRateLimitError("Wait about a minute before requesting another code.")
        )
        ss._active_scrapers["banks - onezero - Acc"] = adapter

        with pytest.raises(BadRequestException, match="Wait about a minute"):
            asyncio.run(service.resend_2fa_code("banks", "onezero", "Acc"))


class TestResend2FACodeFallbackRestart:
    """Providers that can't resend fall back to abort + relaunch."""

    def test_not_supported_aborts_and_restarts(self, service):
        """ResendNotSupportedError → abort old process, start a new one, 'restarted'."""
        adapter = MagicMock()
        adapter.process_id = 100
        adapter.resend_otp = AsyncMock(side_effect=ResendNotSupportedError("nope"))
        ss._active_scrapers["banks - hapoalim - Acc"] = adapter

        with patch.object(service, "abort_scraping_process") as abort, patch.object(
            service, "start_scraping_single", return_value=101
        ) as start:
            result = asyncio.run(
                service.resend_2fa_code("banks", "hapoalim", "Acc")
            )

        abort.assert_called_once_with(100)
        # Relaunch with no period → auto start date (period arg omitted / None).
        start.assert_called_once_with("banks", "hapoalim", "Acc")
        assert result == {"status": "restarted", "process_id": 101}
