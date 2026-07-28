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
- State-changing requests must carry a same-site ``Origin`` (or none at
  all). Loopback trust means *any* web page the user visits can reach
  this API from their browser: CORS blocks the attacker from *reading*
  the response, but the request still executes. See ``origin_allowed``.
"""

import hmac
import ipaddress
import logging
import os
import secrets
from typing import Iterable, Optional, Set
from urllib.parse import urlsplit

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


# Methods that can change server state. Browsers always attach an ``Origin``
# header to these (unlike GET/HEAD), which is what makes the check below a
# reliable CSRF defence.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def origin_allowed(
    origin: Optional[str],
    host_header: Optional[str],
    cors_origins: Iterable[str],
    allowed_hosts: Iterable[str],
) -> bool:
    """Return True when a state-changing request's ``Origin`` is trustworthy.

    Loopback clients are trusted by connection, which means every website
    the user visits can also reach this API through their browser. CORS
    only stops the attacker from *reading* the response — a cross-origin
    ``POST`` still executes, and a body sent with no ``Content-Type`` (a
    ``Blob`` with an empty type) is parsed by FastAPI as JSON, so the
    preflight that ``application/json`` would have triggered never happens.
    Rejecting foreign origins on unsafe methods closes that hole.

    Parameters
    ----------
    origin : Optional[str]
        The request's ``Origin`` header. ``None``/empty means a non-browser
        client (curl, the desktop app, Playwright's request context) and is
        allowed — those cannot be driven by a hostile web page. The literal
        string ``"null"`` (sandboxed iframe, ``file://`` document) is
        rejected, since it is an origin an attacker can arrange.
    host_header : Optional[str]
        The request's ``Host`` header, used for the same-origin comparison.
        This is what lets the packaged desktop app work on whatever random
        port it picked at launch without any configuration.
    cors_origins : Iterable[str]
        Configured ``CORS_ORIGINS`` entries — the dev server proxies with
        ``changeOrigin``, so its ``Origin`` (``http://localhost:5173``)
        never matches ``Host`` and must be allowlisted explicitly.
    allowed_hosts : Iterable[str]
        The ``Host`` allowlist. An origin whose hostname is already trusted
        there (the tailnet address in ``./start.sh remote``) is accepted on
        any port.

    Returns
    -------
    bool
        True when the request may proceed.
    """
    if not origin:
        return True
    origin = origin.strip()
    if origin.lower() == "null":
        return False

    if origin in set(cors_origins):
        return True

    allowed_host_set = {h.lower() for h in allowed_hosts}
    if "*" in allowed_host_set:
        return True

    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    origin_hostname = (parts.hostname or "").lower()
    if not origin_hostname:
        return False

    # Same-origin: the page was served by this very backend (any port the
    # packaged app happened to pick).
    if origin_hostname == hostname_from_host_header(host_header).strip("[]"):
        return True

    return origin_hostname in allowed_host_set
