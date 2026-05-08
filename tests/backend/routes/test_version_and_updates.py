"""
Endpoint tests for ``GET /api/version`` and ``GET/POST /api/updates/check``.

We mock the network probe at the service layer to keep tests fast and
hermetic. The route's job is to translate ``UpdateInfo`` to the JSON
response shape; the probing logic itself is covered by
``test_update_service``.
"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.update_service import UpdateInfo


class TestVersionRoute:
    """Tests for ``GET /api/version``."""

    def test_returns_version_and_platform(self, test_client) -> None:
        """The version route always returns a populated version + platform."""
        resp = test_client.get("/api/version")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["version"], str)
        assert body["version"]
        assert body["platform"] in {"darwin", "win32", "linux", "linux2"}


class TestUpdatesCheckRoute:
    """Tests for ``GET /api/updates/check`` and the matching ``POST`` form."""

    def test_get_returns_update_info(self, test_client) -> None:
        """The GET endpoint returns the structured probe result verbatim."""
        info = UpdateInfo(
            current="1.15.1",
            latest="1.16.0",
            is_outdated=True,
            asset_url="https://example/finance.dmg",
            html_url="https://github.com/owner/repo/releases/v1.16.0",
            checked_at="2025-01-01T00:00:00Z",
        )
        with patch(
            "backend.routes.updates.UpdateService"
        ) as service_cls:
            service_cls.return_value.check.return_value = info
            resp = test_client.get("/api/updates/check")

        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == "1.15.1"
        assert body["latest"] == "1.16.0"
        assert body["is_outdated"] is True
        assert body["asset_url"] == "https://example/finance.dmg"

    def test_post_forces_a_fresh_probe(self, test_client) -> None:
        """``POST /api/updates/check`` calls the service with force=True."""
        info = UpdateInfo(current="1.15.1", error="unavailable")
        with patch(
            "backend.routes.updates.UpdateService"
        ) as service_cls:
            service_cls.return_value.check.return_value = info
            resp = test_client.post("/api/updates/check")

        assert resp.status_code == 200
        # The service must have been asked to refresh.
        service_cls.return_value.check.assert_called_once_with(force=True)
        body = resp.json()
        assert body["error"] == "unavailable"
        assert body["is_outdated"] is False
