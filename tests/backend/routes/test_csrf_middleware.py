"""Middleware-level CSRF tests.

``tests/backend/unit/utils/test_auth.py`` covers ``origin_allowed`` in
isolation; these exercise the wiring in ``backend.main`` so a middleware
that stops being registered (or starts running after the route) fails the
suite rather than silently reopening the hole.

The attack these lock down: the app trusts loopback clients by connection,
so any page the user visits can reach the API from their browser. CORS only
stops the attacker *reading* the response — a cross-origin ``POST`` still
executes, and a body sent with no ``Content-Type`` (a ``Blob`` with an empty
type) is parsed by FastAPI as JSON, so the preflight that
``application/json`` would have forced never happens.

Every write here targets ``/api/backups/`` with ``backup_db`` patched out,
so a request that *passes* the guard never creates or prunes real backup
files — the assertions are on exact status codes, and a 200 proves the
request reached the handler.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

EVIL = "https://evil.example.com"


@pytest.fixture
def fake_backup(tmp_path):
    """Patch the route's ``backup_db`` so allowed writes stay side-effect free."""
    backup_file = tmp_path / "data_20260101_000000.db"
    backup_file.write_bytes(b"x" * 16)
    with patch("backend.routes.backup.backup_db", return_value=Path(backup_file)) as spy:
        yield spy


class TestCsrfMiddleware:
    """Cross-origin state-changing requests are rejected at the middleware."""

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_unsafe_methods_reject_foreign_origin(self, test_client, fake_backup, method):
        """Verify every state-changing verb is blocked from a foreign origin."""
        response = getattr(test_client, method)(
            "/api/backups/", headers={"Origin": EVIL}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"
        fake_backup.assert_not_called()

    def test_no_content_type_json_body_is_blocked(self, test_client):
        """Verify the Blob(type:'') preflight-dodge is rejected.

        Without the middleware this reaches the handler: FastAPI parses a
        body with no ``Content-Type`` as JSON.
        """
        with patch("backend.routes.backup.restore_backup") as restore:
            response = test_client.post(
                "/api/backups/restore",
                content=b'{"filename": "data_20260101_000000.db"}',
                headers={"Origin": EVIL, "Content-Type": ""},
            )
        assert response.status_code == 403
        restore.assert_not_called()

    def test_null_origin_is_blocked(self, test_client, fake_backup):
        """Verify sandboxed-iframe / file:// origins are rejected."""
        response = test_client.post("/api/backups/", headers={"Origin": "null"})
        assert response.status_code == 403
        fake_backup.assert_not_called()

    def test_request_without_origin_is_allowed(self, test_client, fake_backup):
        """Verify non-browser clients (desktop app, curl) still work."""
        response = test_client.post("/api/backups/")
        assert response.status_code == 200
        fake_backup.assert_called_once()

    def test_same_origin_request_is_allowed(self, test_client, fake_backup):
        """Verify the SPA served by this backend is not blocked."""
        response = test_client.post(
            "/api/backups/", headers={"Origin": "http://testserver"}
        )
        assert response.status_code == 200

    def test_dev_proxy_origin_is_allowed(self, test_client, fake_backup):
        """Verify the Vite dev server origin is accepted."""
        response = test_client.post(
            "/api/backups/", headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code == 200

    def test_other_localhost_port_is_rejected(self, test_client, fake_backup):
        """Verify a page on a *different* loopback port cannot issue writes.

        Loopback trust is by connection, so a hostile page served from any
        other local port (a dev server, another app) is exactly the kind of
        origin the guard exists for — same hostname is not same origin.
        """
        response = test_client.post(
            "/api/backups/", headers={"Origin": "http://testserver:9999"}
        )
        assert response.status_code == 403
        fake_backup.assert_not_called()

    def test_safe_methods_are_untouched(self, test_client):
        """Verify GET is not blocked — CORS already stops the response read."""
        with patch("backend.routes.backup.list_backups", return_value=[]):
            response = test_client.get("/api/backups/", headers={"Origin": EVIL})
        assert response.status_code == 200

    def test_non_api_paths_are_untouched(self, test_client):
        """Verify the guard is scoped to /api/ and does not affect the SPA."""
        response = test_client.get("/health", headers={"Origin": EVIL})
        assert response.status_code == 200
