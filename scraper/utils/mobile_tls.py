"""Mobile-app TLS fingerprinting for APIs behind Cloudflare bot management.

Some Israeli bank APIs (One Zero / ``tfd-bank.com``) are the backend for a
mobile app and nothing else. Cloudflare bot management on those hosts scores
the TLS ClientHello fingerprint (JA3), and a default HTTP-client handshake —
whose cipher order matches no shipping mobile app — gets challenged or blocked
outright.

Presenting OkHttp's cipher ordering plus its headers makes the handshake look
like the Android app the API expects. See upstream israeli-bank-scrapers
PR #1128, which hit the same wall from Node.

Caveat: this is a partial match, not a forged JA3. Python's ``ssl`` module
exposes no binding for ``SSL_CTX_set_ciphersuites`` (TLS 1.3 suite order) or
``SSL_CTX_set1_sigalgs_list`` (signature algorithms), so those parts of the
fingerprint stay at OpenSSL's defaults. It moves the needle on the TLS 1.2
cipher list and the headers; it does not make the client indistinguishable.
"""

import logging
import ssl

import httpx

logger = logging.getLogger(__name__)

# Android OkHttp 4.x TLS 1.2 cipher order. TLS 1.3 suites are omitted — they
# are not settable through ``SSLContext.set_ciphers``.
ANDROID_CIPHERS = ":".join([
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "ECDHE-RSA-AES128-SHA",
    "ECDHE-RSA-AES256-SHA",
    "AES128-GCM-SHA256",
    "AES256-GCM-SHA384",
    "AES128-SHA",
    "AES256-SHA",
])

MOBILE_HEADERS = {
    "User-Agent": "okhttp/4.10.0",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive",
}


def build_mobile_ssl_context() -> ssl.SSLContext:
    """Build an SSL context presenting OkHttp's TLS 1.2 cipher ordering.

    Returns
    -------
    ssl.SSLContext
        A verifying context with the Android cipher order applied. Falls back
        to the default cipher list if this OpenSSL build rejects the string
        (e.g. a security level that filters every listed suite) — a working
        connection with the wrong fingerprint beats no connection at all.
    """
    context = httpx.create_ssl_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.set_ciphers(ANDROID_CIPHERS)
    except ssl.SSLError as exc:
        logger.warning(
            "Could not apply the Android cipher order, using OpenSSL defaults: %s",
            exc,
        )
    return context


def build_mobile_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Build an httpx client that handshakes and identifies like the mobile app.

    Parameters
    ----------
    timeout : float
        Request timeout in seconds.

    Returns
    -------
    httpx.AsyncClient
        Client carrying the mobile TLS context and OkHttp headers.
    """
    return httpx.AsyncClient(
        verify=build_mobile_ssl_context(),
        headers=MOBILE_HEADERS,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    )
