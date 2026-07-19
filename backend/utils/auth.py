"""API access-control helpers: remote-client token auth and host allowlist.

The app is a localhost-first personal dashboard with no user accounts, so
its security model is connection-based:

- Requests from the local machine (loopback / unix-socket clients) are
  trusted — the desktop app and dev servers all live there.
- Requests from anywhere else (``./start.sh prod`` bound beyond localhost,
  a phone on the tailnet hitting the backend directly) must present a
  bearer token. The token is generated once, stored in
  ``<user-dir>/api_token`` (0600), and handed to the browser via a
  one-time ``?apiToken=`` URL parameter that the frontend persists.
- Every request must carry an allowlisted ``Host`` header. This blocks
  DNS-rebinding attacks, where a malicious website re-points its own
  domain at 127.0.0.1 to reach the API from the victim's browser —
  such requests arrive from loopback (so token auth doesn't apply) but
  carry the attacker's hostname in ``Host``.
"""

import hmac
import ipaddress
import logging
import os
import secrets
from typing import Iterable, Optional, Set

logger = logging.getLogger(__name__)

API_TOKEN_FILENAME = "api_token"

_DEFAULT_ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "[::1]",
    # Starlette's TestClient sends Host: testserver.
    "testserver",
}


def _base_user_dir() -> str:
    """Resolve the non-demo user directory without importing AppConfig state."""
    return os.environ.get(
        "FAD_USER_DIR",
        os.path.join(os.path.expanduser("~"), ".finance-analysis"),
    )


def get_api_token() -> Optional[str]:
    """Return the configured API token, or None when remote access is off.

    Resolution order: ``FAD_API_TOKEN`` env var, then the
    ``<user-dir>/api_token`` file. No token means remote (non-loopback)
    clients are denied outright.
    """
    env_token = os.environ.get("FAD_API_TOKEN")
    if env_token:
        return env_token
    token_path = os.path.join(_base_user_dir(), API_TOKEN_FILENAME)
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
        return token or None
    except OSError:
        return None


def get_or_create_api_token() -> str:
    """Return the persisted API token, generating one on first use.

    The token file is created with owner-only permissions.
    """
    existing = get_api_token()
    if existing:
        return existing
    user_dir = _base_user_dir()
    os.makedirs(user_dir, exist_ok=True)
    token = secrets.token_urlsafe(32)
    token_path = os.path.join(user_dir, API_TOKEN_FILENAME)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(token)
    try:
        os.chmod(token_path, 0o600)
    except OSError:  # pragma: no cover - e.g. exotic filesystems
        pass
    logger.info("Generated new API access token at %s", token_path)
    return token


def is_trusted_client(client_host: Optional[str]) -> bool:
    """Return True when the TCP peer is the local machine itself.

    Parameters
    ----------
    client_host : Optional[str]
        ``request.client.host`` — None for unix-socket connections (local
        by definition), ``"testclient"`` under Starlette's TestClient.
    """
    if client_host is None:
        return True
    if client_host in ("localhost", "testclient"):
        return True
    try:
        return ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        return False


def token_matches(supplied: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time comparison of a supplied bearer token."""
    if not supplied or not expected:
        return False
    return hmac.compare_digest(supplied.encode(), expected.encode())


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization_header:
        return None
    scheme, _, value = authorization_header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


def build_allowed_hosts(env_value: Optional[str] = None) -> Set[str]:
    """Build the Host-header allowlist from the ``ALLOWED_HOSTS`` env var.

    Parameters
    ----------
    env_value : Optional[str]
        Comma-separated extra hostnames/IPs. ``"*"`` disables host
        checking entirely (the set then contains ``"*"``).

    Returns
    -------
    Set[str]
        Lowercased allowed hostnames, always including the localhost
        defaults.
    """
    allowed = set(_DEFAULT_ALLOWED_HOSTS)
    raw = env_value if env_value is not None else os.environ.get("ALLOWED_HOSTS", "")
    for entry in raw.split(","):
        entry = entry.strip().lower()
        if entry:
            allowed.add(entry)
    return allowed


def hostname_from_host_header(host_header: Optional[str]) -> str:
    """Extract the bare hostname from a ``Host`` header (strip the port).

    Handles bracketed IPv6 literals (``[::1]:8000`` → ``[::1]``).
    """
    if not host_header:
        return ""
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        end = host_header.find("]")
        return host_header[: end + 1] if end != -1 else host_header
    if host_header.count(":") == 1:
        return host_header.rsplit(":", 1)[0]
    return host_header


def host_allowed(host_header: Optional[str], allowed: Iterable[str]) -> bool:
    """Return True when the request's Host header is on the allowlist."""
    allowed_set = set(allowed)
    if "*" in allowed_set:
        return True
    return hostname_from_host_header(host_header) in allowed_set
