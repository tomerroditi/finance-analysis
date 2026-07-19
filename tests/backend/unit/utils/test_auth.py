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
