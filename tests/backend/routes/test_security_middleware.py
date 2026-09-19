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


class TestProxiedLocalRequests:
    """Tests for requests a local reverse proxy (tailscale serve) relayed.

    The TestClient connects as a local client, which is exactly what
    tailscaled looks like when uvicorn runs with ``--no-proxy-headers``.
    """

    RELAYED = {"X-Forwarded-For": "100.101.102.103"}

    @pytest.fixture(autouse=True)
    def owner_allowlisted(self, monkeypatch, tmp_path):
        """Allowlist one tailnet user and leave no token configured."""
        monkeypatch.setattr(
            backend_main,
            "_tailnet_users",
            auth.build_tailnet_users(env_value="me@example.com"),
        )
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)

    def test_relayed_request_loses_local_trust(self, test_client):
        """Verify a forwarded request from loopback is not trusted as local."""
        response = test_client.get("/api/transactions/", headers=self.RELAYED)
        assert response.status_code == 401

    def test_allowlisted_tailnet_user_is_admitted(self, test_client):
        """Verify the identity tailscale serve vouches for grants access."""
        response = test_client.get(
            "/api/transactions/",
            headers={**self.RELAYED, "Tailscale-User-Login": "me@example.com"},
        )
        assert response.status_code == 200

    def test_other_tailnet_user_is_rejected(self, test_client):
        """Verify a different tailnet user (e.g. a shared-in node) needs a token."""
        response = test_client.get(
            "/api/transactions/",
            headers={**self.RELAYED, "Tailscale-User-Login": "guest@example.com"},
        )
        assert response.status_code == 401

    def test_relayed_request_with_token_passes(self, test_client, monkeypatch):
        """Verify a relayed client can still authenticate with the token."""
        monkeypatch.setenv("FAD_API_TOKEN", "correct-token")
        response = test_client.get(
            "/api/transactions/",
            headers={**self.RELAYED, "Authorization": "Bearer correct-token"},
        )
        assert response.status_code == 200

    def test_login_header_from_a_remote_peer_is_ignored(
        self, test_client, monkeypatch
    ):
        """Verify a non-local peer can't claim a tailnet identity itself.

        Only this machine's tailscaled connects from loopback, so the header
        is only believed there; anyone reaching a 0.0.0.0-bound server
        directly still needs the token.
        """
        monkeypatch.setattr(
            "backend.utils.auth.is_trusted_client", lambda host: False
        )
        response = test_client.get(
            "/api/transactions/",
            headers={"Tailscale-User-Login": "me@example.com"},
        )
        assert response.status_code == 401


class TestRequestSizeLimitMiddleware:
    """Tests for the request body size cap, including chunked bodies."""

    @staticmethod
    def _chunked(total_bytes: int, chunk_size: int = 4096):
        """Yield ``total_bytes`` of filler in chunks (forces chunked encoding)."""
        sent = 0
        while sent < total_bytes:
            size = min(chunk_size, total_bytes - sent)
            sent += size
            yield b"x" * size

    def test_declared_oversize_body_is_rejected(self, test_client, monkeypatch):
        """A Content-Length above the cap returns 413."""
        monkeypatch.setattr(backend_main, "_MAX_REQUEST_BYTES", 1024)
        response = test_client.post(
            "/api/transactions/",
            content=b"x" * 4096,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413

    def test_invalid_content_length_is_rejected(self, test_client):
        """A non-numeric Content-Length returns 400."""
        response = test_client.post(
            "/api/transactions/",
            content=b"{}",
            headers={"Content-Length": "not-a-number"},
        )
        assert response.status_code == 400

    def test_chunked_oversize_body_is_rejected(self, test_client, monkeypatch):
        """A chunked body over the cap returns 413 instead of being processed.

        Without a Content-Length header the middleware previously waved the
        request through and the full body was buffered and parsed.
        """
        monkeypatch.setattr(backend_main, "_MAX_REQUEST_BYTES", 1024)
        response = test_client.post(
            "/api/transactions/",
            content=self._chunked(64 * 1024),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413

    def test_chunked_body_under_cap_is_still_readable(self, test_client):
        """A chunked body under the cap reaches the endpoint intact."""
        payload = (
            b'{"date": "2024-06-01", "description": "Chunked", "amount": -12.5,'
            b' "account_name": "Wallet", "service": "cash"}'
        )

        def stream():
            yield payload[:20]
            yield payload[20:]

        response = test_client.post(
            "/api/transactions/",
            content=stream(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200

        txns = test_client.get("/api/transactions/", params={"service": "cash"}).json()
        assert any(t["description"] == "Chunked" for t in txns)


class TestDocsEndpointsAreTokenGuarded:
    """Tests that OpenAPI/docs endpoints require a token for remote clients."""

    @pytest.fixture
    def untrusted_client(self, monkeypatch):
        """Make the middleware treat every connection as remote."""
        monkeypatch.setattr(
            "backend.utils.auth.is_trusted_client", lambda host: False
        )

    @pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
    def test_docs_paths_require_token_for_remote_clients(
        self, test_client, untrusted_client, monkeypatch, tmp_path, path
    ):
        """A remote client with no token cannot enumerate the API surface."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        response = test_client.get(path)
        assert response.status_code == 401

    @pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
    def test_docs_paths_open_for_local_clients(self, test_client, path):
        """Loopback clients keep unauthenticated access to the docs."""
        response = test_client.get(path)
        assert response.status_code == 200

    def test_docs_paths_accept_valid_token(
        self, test_client, untrusted_client, monkeypatch
    ):
        """A remote client with the configured token can read the schema."""
        monkeypatch.setenv("FAD_API_TOKEN", "correct-token")
        response = test_client.get(
            "/openapi.json", headers={"Authorization": "Bearer correct-token"}
        )
        assert response.status_code == 200
