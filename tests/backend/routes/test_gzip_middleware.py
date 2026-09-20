"""Tests for response compression.

The dashboard pulls well over a megabyte of JSON per load and the production
build serves a similar weight of JS/CSS from ``/assets``. Uncompressed, that
is seconds of transfer on a phone before anything renders; this JSON shape
compresses roughly 11:1.
"""


class TestGZipMiddleware:
    """Compression must be on, honour the client, and leave small bodies alone."""

    def test_large_response_is_compressed(self, test_client):
        """A body over the threshold comes back gzipped for a willing client."""
        response = test_client.get(
            "/openapi.json", headers={"accept-encoding": "gzip"}
        )

        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"

    def test_compressed_response_still_decodes(self, test_client):
        """Compression is transport-only — the payload must be unchanged."""
        response = test_client.get(
            "/openapi.json", headers={"accept-encoding": "gzip"}
        )

        assert response.json()["info"]["title"] == "Finance Analysis API"

    def test_client_that_cannot_decompress_gets_plain_bytes(self, test_client):
        """A client not advertising gzip must not be handed a gzipped body."""
        response = test_client.get(
            "/openapi.json", headers={"accept-encoding": "identity"}
        )

        assert response.status_code == 200
        assert "content-encoding" not in response.headers

    def test_small_response_is_not_compressed(self, test_client):
        """Below the threshold, framing costs more than it saves."""
        response = test_client.get("/health", headers={"accept-encoding": "gzip"})

        assert response.status_code == 200
        assert "content-encoding" not in response.headers
