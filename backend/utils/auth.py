"""API access-control helpers: remote-client token auth and host allowlist.

The app is a localhost-first personal dashboard with no user accounts, so
its security model is connection-based:

- Requests from the local machine (loopback / unix-socket clients) are
  trusted — the desktop app and dev servers all live there — unless a
  local reverse proxy relayed them from elsewhere (``is_proxied_request``).
- Requests relayed by ``tailscale serve`` are admitted when the tailnet
  identity it vouches for is allowlisted (``TAILNET_ALLOWED_USERS``, set
  by ``./start.sh prod`` to this machine's Tailscale owner).
- Requests from anywhere else (``./start.sh prod`` bound beyond localhost,
  another tailnet user) must present a bearer token. The token is generated once, stored in
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
from typing import Iterable, Mapping, Optional, Set
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

API_TOKEN_FILENAME = "api_token"

_PROXY_HEADERS = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "tailscale-user-login",
    "x-forwarded-host",
    "x-forwarded-proto",
    "via",
    "cf-connecting-ip",
    "true-client-ip",
)

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
    os.makedirs(user_dir, mode=0o700, exist_ok=True)
    token = secrets.token_urlsafe(32)
    token_path = os.path.join(user_dir, API_TOKEN_FILENAME)
    # Created owner-only rather than chmod-ed after the write, which would
    # leave the token readable under the default umask in between.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
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
        address = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def is_proxied_request(headers: Mapping[str, str]) -> bool:
    """Return True when a local proxy relayed the request from elsewhere.

    A reverse proxy on this machine (``tailscale serve``, Caddy, nginx)
    connects from loopback, so without this check whatever it relays would
    inherit local trust. HTTP proxies announce themselves in one of these
    headers; uvicorn must run with ``--no-proxy-headers`` for the TCP peer
    to still be the proxy — with proxy headers on, uvicorn already reports
    the forwarded client, which is then simply not local.

    Raw TCP forwarders (``ssh -L``, socat, ``tailscale serve --tcp``) add no
    headers and cannot be told apart from a local client: never point one
    at this server.

    Parameters
    ----------
    headers : Mapping[str, str]
        The request headers (case-insensitive mapping).
    """
    return any(headers.get(name) for name in _PROXY_HEADERS)


def build_tailnet_users(env_value: Optional[str] = None) -> Set[str]:
    """Build the tailnet-login allowlist from ``TAILNET_ALLOWED_USERS``.

    Parameters
    ----------
    env_value : Optional[str]
        Comma-separated Tailscale login names (e.g. ``me@example.com``).

    Returns
    -------
    Set[str]
        Lowercased logins; empty when unset, which admits nobody.
    """
    raw = (
        env_value
        if env_value is not None
        else os.environ.get("TAILNET_ALLOWED_USERS", "")
    )
    return {entry.strip().lower() for entry in raw.split(",") if entry.strip()}


def build_tailnet_ingress_port(env_value: Optional[str] = None) -> Optional[int]:
    """Read the loopback port reserved for ``tailscale serve`` traffic.

    Parameters
    ----------
    env_value : Optional[str]
        Value of ``TAILNET_INGRESS_PORT``; read from the environment when
        None.

    Returns
    -------
    Optional[int]
        The port, or None when unset or malformed — which trusts no
        ``Tailscale-User-Login`` header at all.
    """
    raw = (
        env_value
        if env_value is not None
        else os.environ.get("TAILNET_INGRESS_PORT", "")
    )
    try:
        port = int(raw.strip())
    except ValueError:
        return None
    return port if 0 < port < 65536 else None


def arrived_on_tailnet_ingress(
    server: Optional[tuple], ingress_port: Optional[int]
) -> bool:
    """Return True when a request came in on the ``tailscale serve`` listener.

    ``tailscale serve`` strips any client copy of ``Tailscale-User-Login``,
    but another local proxy (Caddy, ngrok, cloudflared) passes it through,
    so the header is only proof of identity on a listener nothing but
    tailscaled connects to. ``./start.sh prod`` opens that listener on its
    own loopback port and points ``tailscale serve`` at it.

    Parameters
    ----------
    server : Optional[tuple]
        The ASGI scope's ``server`` — the local ``(host, port)`` the
        connection was accepted on.
    ingress_port : Optional[int]
        From ``build_tailnet_ingress_port``.
    """
    if ingress_port is None or not server or len(server) < 2:
        return False
    return server[1] == ingress_port


def tailnet_user_allowed(login: Optional[str], allowed: Iterable[str]) -> bool:
    """Return True when ``tailscale serve`` vouched for an allowlisted user.

    ``tailscale serve`` sets ``Tailscale-User-Login`` to the verified
    identity of the tailnet user behind the request and strips any copy the
    client sent, so the header is trustworthy on a request relayed by this
    machine's own tailscaled. It is absent for tagged devices and Funnel
    (public internet) traffic, which therefore fall back to token auth.

    Parameters
    ----------
    login : Optional[str]
        The ``Tailscale-User-Login`` header value.
    allowed : Iterable[str]
        Lowercased logins from ``build_tailnet_users``.
    """
    return bool(login) and login.strip().lower() in set(allowed)


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


def port_from_host_header(host_header: Optional[str]) -> Optional[int]:
    """Extract the port from a ``Host`` header, or None when it omits one.

    Handles bracketed IPv6 literals (``[::1]:8000`` -> 8000). A malformed
    port is reported as None rather than raising, so callers treat it the
    same as an absent one.

    Parameters
    ----------
    host_header : Optional[str]
        The request's ``Host`` header.

    Returns
    -------
    int or None
        The port, or None when the header carries no parsable port.
    """
    if not host_header:
        return None
    host_header = host_header.strip()
    if host_header.startswith("["):
        end = host_header.find("]")
        if end == -1 or not host_header[end + 1 :].startswith(":"):
            return None
        raw = host_header[end + 2 :]
    elif host_header.count(":") == 1:
        raw = host_header.rsplit(":", 1)[1]
    else:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


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
        never matches ``Host`` and must be allowlisted explicitly. So is
        the tailnet URL ``./start.sh prod`` shares via ``tailscale serve``.
        A Host-allowlisted hostname is never enough on its own — not even
        ``ALLOWED_HOSTS=*``, which only switches off the Host check — so a
        hostile page on another port of a trusted host cannot issue writes.

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

    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    origin_hostname = (parts.hostname or "").lower()
    if not origin_hostname:
        return False

    # Same-origin: the page was served by this very backend, on the very
    # port it is listening on. Comparing the whole authority still lets the
    # packaged app work on whatever port it picked at launch (the browser
    # reports that same port in both headers), while a hostile page on
    # another loopback port no longer counts as same-origin.
    # The app is always served over plain HTTP (uvicorn is never given a
    # certificate), so a ``Host`` header with no port means port 80. Pinning
    # it that way keeps ``https://localhost`` -- a different origin the
    # backend cannot have served -- from passing as same-origin.
    origin_scheme = (parts.scheme or "").lower()
    origin_port = parts.port
    if origin_port is None:
        origin_port = 443 if origin_scheme == "https" else 80
    host_port = port_from_host_header(host_header)
    if host_port is None:
        host_port = 80
    if (
        origin_hostname == hostname_from_host_header(host_header).strip("[]")
        and origin_port == host_port
    ):
        return True

    return False
