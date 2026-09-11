"""Unit tests for API access-control helpers (backend/utils/auth.py)."""

import os
import stat

import pytest

from backend.utils import auth


class TestIsTrustedClient:
    """Tests for loopback/local client detection."""

    @pytest.mark.parametrize(
        "host", [None, "127.0.0.1", "127.0.0.5", "::1", "localhost", "testclient"]
    )
    def test_local_clients_are_trusted(self, host):
        """Verify loopback addresses and local sentinels are trusted."""
        assert auth.is_trusted_client(host) is True

    @pytest.mark.parametrize(
        "host", ["192.168.1.10", "10.0.0.2", "203.0.113.5", "evil.example.com", ""]
    )
    def test_remote_clients_are_not_trusted(self, host):
        """Verify non-loopback peers are untrusted."""
        assert auth.is_trusted_client(host) is False


class TestTokenHelpers:
    """Tests for bearer extraction and constant-time comparison."""

    def test_extract_bearer_token(self):
        """Verify a well-formed Bearer header yields its token."""
        assert auth.extract_bearer_token("Bearer abc123") == "abc123"
        assert auth.extract_bearer_token("bearer abc123") == "abc123"

    @pytest.mark.parametrize(
        "header", [None, "", "Basic abc123", "Bearer", "Bearer   "]
    )
    def test_extract_bearer_token_rejects_malformed(self, header):
        """Verify missing/non-bearer headers yield None."""
        assert auth.extract_bearer_token(header) is None

    def test_token_matches(self):
        """Verify matching tokens pass and everything else fails."""
        assert auth.token_matches("secret", "secret") is True
        assert auth.token_matches("secret", "other") is False
        assert auth.token_matches(None, "secret") is False
        assert auth.token_matches("secret", None) is False
        assert auth.token_matches("", "") is False


class TestApiTokenStorage:
    """Tests for token resolution and creation."""

    def test_env_var_wins_over_file(self, monkeypatch, tmp_path):
        """Verify FAD_API_TOKEN takes precedence over the token file."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        (tmp_path / auth.API_TOKEN_FILENAME).write_text("file-token")
        monkeypatch.setenv("FAD_API_TOKEN", "env-token")
        assert auth.get_api_token() == "env-token"

    def test_reads_token_file(self, monkeypatch, tmp_path):
        """Verify the token file is read when no env var is set."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        (tmp_path / auth.API_TOKEN_FILENAME).write_text("file-token\n")
        assert auth.get_api_token() == "file-token"

    def test_no_token_configured_returns_none(self, monkeypatch, tmp_path):
        """Verify None when neither env var nor file exists."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)
        assert auth.get_api_token() is None

    def test_get_or_create_generates_owner_only_file(self, monkeypatch, tmp_path):
        """Verify first call creates a 0600 token file, second call reuses it."""
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
        monkeypatch.delenv("FAD_API_TOKEN", raising=False)

        token = auth.get_or_create_api_token()

        token_path = tmp_path / auth.API_TOKEN_FILENAME
        assert token_path.read_text() == token
        assert len(token) >= 32
        mode = stat.S_IMODE(os.stat(token_path).st_mode)
        assert mode == 0o600
        assert auth.get_or_create_api_token() == token


class TestHostAllowlist:
    """Tests for Host-header parsing and allowlisting."""

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("localhost:8000", "localhost"),
            ("127.0.0.1", "127.0.0.1"),
            ("[::1]:8000", "[::1]"),
            ("[::1]", "[::1]"),
            ("Example.COM:443", "example.com"),
            (None, ""),
            ("", ""),
        ],
    )
    def test_hostname_from_host_header(self, header, expected):
        """Verify port stripping, including bracketed IPv6 literals."""
        assert auth.hostname_from_host_header(header) == expected

    def test_defaults_allow_localhost_variants(self):
        """Verify the default allowlist covers local dev and TestClient."""
        allowed = auth.build_allowed_hosts(env_value="")
        for host in ("localhost:5173", "127.0.0.1:8000", "[::1]:8000", "testserver"):
            assert auth.host_allowed(host, allowed) is True

    def test_unknown_host_is_rejected(self):
        """Verify a foreign hostname (DNS-rebinding vector) is rejected."""
        allowed = auth.build_allowed_hosts(env_value="")
        assert auth.host_allowed("attacker.example.com:8000", allowed) is False
        assert auth.host_allowed("", allowed) is False

    def test_env_extends_allowlist(self):
        """Verify ALLOWED_HOSTS entries are added case-insensitively."""
        allowed = auth.build_allowed_hosts(env_value="100.64.0.7, My-Laptop.local")
        assert auth.host_allowed("100.64.0.7:5174", allowed) is True
        assert auth.host_allowed("my-laptop.LOCAL:8080", allowed) is True

    def test_wildcard_disables_check(self):
        """Verify '*' allows every host (trusted-proxy deployments)."""
        allowed = auth.build_allowed_hosts(env_value="*")
        assert auth.host_allowed("anything.example.com", allowed) is True


class TestOriginAllowed:
    """Origin validation for state-changing requests (CSRF defence)."""

    CORS = ["http://localhost:5173", "http://127.0.0.1:5173"]
    HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "testserver"}

    def _check(self, origin, host="localhost:8000", cors=None, hosts=None):
        """Run origin_allowed with this class's default CORS/host allowlists."""
        return auth.origin_allowed(
            origin,
            host,
            self.CORS if cors is None else cors,
            self.HOSTS if hosts is None else hosts,
        )

    def test_absent_origin_is_allowed(self):
        """Verify non-browser clients (curl, desktop app) are not blocked."""
        assert self._check(None) is True
        assert self._check("") is True

    def test_foreign_origin_is_rejected(self):
        """Verify a hostile site cannot drive state-changing requests."""
        assert self._check("https://evil.example.com") is False

    def test_lookalike_origin_is_rejected(self):
        """Verify suffix/prefix lookalike hostnames do not slip through."""
        assert self._check("http://localhost.evil.com") is False
        assert self._check("http://notlocalhost") is False

    def test_null_origin_is_rejected(self):
        """Verify sandboxed iframes / file:// documents are rejected."""
        assert self._check("null") is False
        assert self._check("NULL") is False

    def test_same_origin_is_allowed_on_whatever_port_it_serves(self):
        """Verify the packaged app works on whatever port it picked.

        The browser reports that same port in both ``Origin`` and ``Host``,
        so comparing the whole authority costs the packaged app nothing.
        """
        assert self._check("http://localhost:8000", host="localhost:8000") is True
        assert self._check("http://localhost:49821", host="localhost:49821") is True

    def test_same_host_on_another_port_is_rejected(self):
        """Verify a page on a different loopback port is not same-origin.

        Loopback trust is per connection, so any other local server -- a
        second dev server, an unrelated desktop app -- is exactly the
        attacker this guard exists to stop. Same hostname is not same
        origin.
        """
        assert self._check("http://localhost:9999", host="localhost:8000") is False
        assert self._check("http://127.0.0.1:5555", host="127.0.0.1:8000") is False

    def test_default_port_origin_matches_portless_host(self):
        """Verify an implicit port 80 matches a Host header with no port."""
        assert self._check("http://localhost", host="localhost") is True
        assert self._check("https://localhost", host="localhost") is False

    def test_dev_proxy_origin_is_allowed(self):
        """Verify the Vite dev server origin survives changeOrigin proxying."""
        assert self._check("http://localhost:5173", host="127.0.0.1:8000") is True

    def test_allowlisted_host_alone_does_not_authorise_an_origin(self):
        """Verify Host-allowlisting a tailnet IP does not trust every port on it.

        ``./start.sh remote`` puts the tailnet *frontend* origin into
        ``CORS_ORIGINS``, which is what authorises it. Trusting the bare
        hostname on any port would hand every other service on that host a
        write channel.
        """
        hosts = self.HOSTS | {"100.64.0.7"}
        assert self._check("http://100.64.0.7:5174", hosts=hosts) is False

    def test_tailnet_frontend_is_allowed_through_cors_origins(self):
        """Verify the remote-mode tailnet frontend still reaches the API.

        This is the path ``./start.sh remote`` configures, and it is how the
        origin above is meant to be authorised.
        """
        cors = self.CORS + ["http://100.64.0.7:5174"]
        assert (
            self._check(
                "http://100.64.0.7:5174", host="100.64.0.7:8001", cors=cors
            )
            is True
        )

    def test_ipv6_same_origin_is_allowed(self):
        """Verify bracketed IPv6 Host literals match their Origin form."""
        assert self._check("http://[::1]:8000", host="[::1]:8000") is True

    def test_wildcard_host_allowlist_disables_check(self):
        """Verify '*' (trusted-proxy deployments) accepts any origin."""
        assert self._check("https://evil.example.com", hosts={"*"}) is True

    def test_malformed_origin_is_rejected(self):
        """Verify unparseable / hostless origins fail closed."""
        assert self._check("not a url") is False
        assert self._check("http://") is False

    def test_unsafe_methods_cover_state_changers(self):
        """Verify the guarded method set is exactly the state-changing verbs."""
        assert auth.UNSAFE_METHODS == {"POST", "PUT", "PATCH", "DELETE"}
        assert "GET" not in auth.UNSAFE_METHODS
        assert "OPTIONS" not in auth.UNSAFE_METHODS
