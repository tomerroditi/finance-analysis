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
"""

import pytest

EVIL = "https://evil.example.com"


class TestCsrfMiddleware:
    """Cross-origin state-changing requests are rejected at the middleware."""

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_unsafe_methods_reject_foreign_origin(self, test_client, method):
        """Verify every state-changing verb is blocked from a foreign origin."""
        response = getattr(test_client, method)(
            "/api/backups/", headers={"Origin": EVIL}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"

    def test_no_content_type_json_body_is_blocked(self, test_client):
        """Verify the Blob(type:'') preflight-dodge is rejected.

        Without the middleware this reaches the handler: FastAPI parses a
        body with no ``Content-Type`` as JSON.
        """
        response = test_client.post(
            "/api/testing/toggle_demo_mode",
            content=b'{"enabled": true}',
            headers={"Origin": EVIL, "Content-Type": ""},
        )
        assert response.status_code == 403

    def test_null_origin_is_blocked(self, test_client):
        """Verify sandboxed-iframe / file:// origins are rejected."""
        response = test_client.post("/api/backups/", headers={"Origin": "null"})
        assert response.status_code == 403

    def test_request_without_origin_is_allowed(self, test_client):
        """Verify non-browser clients (desktop app, curl) still work."""
        response = test_client.post("/api/backups/")
        assert response.status_code != 403

    def test_same_origin_request_is_allowed(self, test_client):
        """Verify the SPA served by this backend is not blocked."""
        response = test_client.post(
            "/api/backups/", headers={"Origin": "http://testserver"}
        )
        assert response.status_code != 403

    def test_dev_proxy_origin_is_allowed(self, test_client):
        """Verify the Vite dev server origin is accepted."""
        response = test_client.post(
            "/api/backups/", headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code != 403

    def test_safe_methods_are_untouched(self, test_client):
        """Verify GET is not blocked — CORS already stops the response read."""
        response = test_client.get("/api/backups/", headers={"Origin": EVIL})
        assert response.status_code != 403

    def test_non_api_paths_are_untouched(self, test_client):
        """Verify the guard is scoped to /api/ and does not affect the SPA."""
        response = test_client.get("/health", headers={"Origin": EVIL})
        assert response.status_code == 200
