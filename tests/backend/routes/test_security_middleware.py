"""Tests for the Host-allowlist and remote-client token-auth middlewares."""

import pytest

import backend.main as backend_main
from backend.utils import auth


class TestHostAllowlistMiddleware:
    """Tests for DNS-rebinding protection via the Host header."""

    def test_default_test_host_is_allowed(self, test_client):
        """Verify the TestClient's default Host (testserver) passes."""
        response = test_client.get("/health")
        assert response.status_code == 200

    def test_localhost_host_is_allowed(self, test_client):
        """Verify a localhost Host header passes."""
        response = test_client.get("/health", headers={"host": "localhost:8000"})
        assert response.status_code == 200

    def test_foreign_host_is_rejected(self, test_client):
        """Verify a rebound attacker hostname is rejected with 400."""
        response = test_client.get(
            "/health", headers={"host": "attacker.example.com"}
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid Host header"}

    def test_api_route_with_foreign_host_is_rejected(self, test_client):
        """Verify API routes are covered by the host check too."""
        response = test_client.get(
            "/api/transactions/", headers={"host": "attacker.example.com"}
        )
        assert response.status_code == 400

    def test_allowed_hosts_extension(self, test_client, monkeypatch):
        """Verify an ALLOWED_HOSTS entry admits an extra hostname."""
        monkeypatch.setattr(
            backend_main,
            "_allowed_hosts",
            auth.build_allowed_hosts(env_value="100.64.0.7"),
        )
        response = test_client.get("/health", headers={"host": "100.64.0.7:8080"})
        assert response.status_code == 200


class TestRemoteClientTokenMiddleware:
    """Tests for bearer-token enforcement on non-local clients."""

    @pytest.fixture
    def untrusted_client(self, monkeypatch):
        """Make the middleware treat every connection as remote."""
        monkeypatch.setattr(
            "backend.utils.auth.is_trusted_client", lambda host: False
        )

    def test_local_client_needs_no_token(self, test_client):
        """Verify same-machine requests are exempt from token auth."""
        response = test_client.get("/api/transactions/")
        assert response.status_code == 200

    def test_remote_client_without_token_is_rejected(
        self, test_client, untrusted_client, monkeypatch, tmp_path
    ):
        """Verify a remote client with no token gets 401."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        response = test_client.get("/api/transactions/")
        assert response.status_code == 401

    def test_remote_client_with_wrong_token_is_rejected(
        self, test_client, untrusted_client, monkeypatch
    ):
        """Verify a bad bearer token gets 401."""
        monkeypatch.setenv("FAD_API_TOKEN", "correct-token")
        response = test_client.get(
            "/api/transactions/",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401

    def test_remote_client_with_valid_token_passes(
        self, test_client, untrusted_client, monkeypatch
    ):
        """Verify the configured token grants access."""
        monkeypatch.setenv("FAD_API_TOKEN", "correct-token")
        response = test_client.get(
            "/api/transactions/",
            headers={"Authorization": "Bearer correct-token"},
        )
        assert response.status_code == 200

    def test_non_api_paths_are_not_token_guarded(
        self, test_client, untrusted_client, monkeypatch, tmp_path
    ):
        """Verify the static shell (non-/api paths) stays reachable."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        response = test_client.get("/health")
        assert response.status_code == 200

    def test_options_preflight_is_exempt(
        self, test_client, untrusted_client, monkeypatch, tmp_path
    ):
        """Verify CORS preflight requests bypass token auth."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        response = test_client.options(
            "/api/transactions/",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code != 401
