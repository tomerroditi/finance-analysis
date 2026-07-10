"""Tests for the POST /api/scraping/resend-2fa endpoint.

Verifies the happy path (200 + status dict), rate-limit mapping (400),
not-found mapping (404), and — per .claude/rules/api_paths.md — that the
exact path resolves directly (no 307 trailing-slash redirect).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.errors import BadRequestException, EntityNotFoundException


class TestResend2FARoute:
    """Tests for the resend-2fa scraping endpoint."""

    def test_resend_success_returns_status_dict(self, test_client):
        """POST /api/scraping/resend-2fa returns the service's status dict."""
        instance = MagicMock()
        instance.resend_2fa_code = AsyncMock(
            return_value={"status": "resent", "process_id": 42}
        )
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/resend-2fa",
                json={"service": "banks", "provider": "onezero", "account": "Acc"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "resent", "process_id": 42}
        instance.resend_2fa_code.assert_awaited_once_with("banks", "onezero", "Acc")

    def test_resend_restarted_status_passes_through(self, test_client):
        """A 'restarted' fallback result is returned verbatim."""
        instance = MagicMock()
        instance.resend_2fa_code = AsyncMock(
            return_value={"status": "restarted", "process_id": 99}
        )
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/resend-2fa",
                json={"service": "banks", "provider": "hapoalim", "account": "Acc"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "restarted", "process_id": 99}

    def test_resend_rate_limited_returns_400(self, test_client):
        """A BadRequestException from the service maps to HTTP 400 with the message."""
        instance = MagicMock()
        instance.resend_2fa_code = AsyncMock(
            side_effect=BadRequestException("Wait about a minute before requesting another code.")
        )
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/resend-2fa",
                json={"service": "banks", "provider": "onezero", "account": "Acc"},
            )

        assert resp.status_code == 400
        assert "Wait about a minute" in resp.json()["detail"]

    def test_resend_not_found_returns_404(self, test_client):
        """An EntityNotFoundException maps to HTTP 404 (no waiting scraper)."""
        instance = MagicMock()
        instance.resend_2fa_code = AsyncMock(
            side_effect=EntityNotFoundException("Scraping process not found")
        )
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/resend-2fa",
                json={"service": "banks", "provider": "onezero", "account": "Missing"},
            )

        assert resp.status_code == 404

    def test_resend_exact_path_no_redirect(self, test_client):
        """The exact path resolves with no 307 redirect (redirect_slashes=False).

        Per .claude/rules/api_paths.md, a trailing-slash mismatch would emit a
        307 to an absolute backend URL that the frontend CSP then blocks. The
        client path and the route must agree exactly, so the non-slash path
        must return 200 directly — never 307.
        """
        instance = MagicMock()
        instance.resend_2fa_code = AsyncMock(
            return_value={"status": "resent", "process_id": 1}
        )
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/resend-2fa",
                json={"service": "banks", "provider": "onezero", "account": "Acc"},
                follow_redirects=False,
            )

        assert resp.status_code != 307
        assert resp.status_code == 200
