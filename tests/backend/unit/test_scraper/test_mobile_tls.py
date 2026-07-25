"""Tests for the mobile TLS fingerprinting helper used by the One Zero scraper.

Ported from upstream israeli-bank-scrapers PR #1128, which hit Cloudflare bot
management on ``tfd-bank.com`` scoring the TLS handshake.
"""

import ssl

from scraper.providers.banks.onezero import OneZeroScraper
from scraper.utils import mobile_tls


class TestMobileSslContext:
    """The context presents OkHttp's TLS 1.2 cipher ordering."""

    def test_android_ciphers_lead_the_tls12_list(self):
        """OkHttp's preferred suites come first among the TLS 1.2 ciphers."""
        context = mobile_tls.build_mobile_ssl_context()

        tls12 = [
            c["name"]
            for c in context.get_ciphers()
            if c["protocol"] != "TLSv1.3"
        ]

        assert tls12[0] == "ECDHE-ECDSA-AES128-GCM-SHA256"
        assert tls12[1] == "ECDHE-RSA-AES128-GCM-SHA256"

    def test_tls_floor_is_1_2(self):
        """Nothing older than TLS 1.2 is offered."""
        assert (
            mobile_tls.build_mobile_ssl_context().minimum_version
            is ssl.TLSVersion.TLSv1_2
        )

    def test_certificate_verification_stays_on(self):
        """Fingerprint shaping must not weaken certificate checking."""
        context = mobile_tls.build_mobile_ssl_context()

        assert context.verify_mode is ssl.CERT_REQUIRED
        assert context.check_hostname is True

    def test_unsupported_cipher_string_falls_back(self, monkeypatch):
        """An OpenSSL build rejecting the list still yields a usable context."""

        def raise_ssl_error(_self, _ciphers):
            raise ssl.SSLError("no cipher match")

        monkeypatch.setattr(ssl.SSLContext, "set_ciphers", raise_ssl_error)

        context = mobile_tls.build_mobile_ssl_context()

        assert context.get_ciphers()


class TestMobileClient:
    """The client identifies itself as the Android app."""

    def test_okhttp_headers_are_applied(self):
        """Requests carry OkHttp's User-Agent rather than the httpx default."""
        client = mobile_tls.build_mobile_client()

        assert client.headers["user-agent"] == "okhttp/4.10.0"
        assert client.headers["accept-encoding"] == "gzip"

    def test_redirects_are_followed(self):
        """Identity-server hops still resolve, as with the default client."""
        assert mobile_tls.build_mobile_client().follow_redirects is True


class TestOneZeroUsesMobileClient:
    """One Zero opts into the mobile fingerprint at initialize time."""

    def test_initialize_builds_a_mobile_client(self):
        """The scraper's client carries the OkHttp User-Agent."""
        import asyncio

        scraper = OneZeroScraper.__new__(OneZeroScraper)
        asyncio.run(scraper.initialize())

        try:
            assert scraper.client.headers["user-agent"] == "okhttp/4.10.0"
        finally:
            asyncio.run(scraper.client.aclose())
