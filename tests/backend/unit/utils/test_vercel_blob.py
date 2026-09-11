"""Tests for the hand-rolled Vercel Blob REST client.

There is no Python SDK, so the request shapes below pin the contract the
official ``@vercel/blob`` package speaks (API version, header names, the
``pathname`` query parameter, the JSON delete body, the blob URL layout). A
drift here would only surface on the live deployment, silently, as sandboxes
that never persist.
"""

import json

import httpx
import pytest

from backend.utils import vercel_blob
from backend.utils.vercel_blob import (
    API_VERSION,
    BlobObject,
    VercelBlobClient,
    parse_store_id,
    parse_uploaded_at,
)

TOKEN = "vercel_blob_rw_store123_secretsecret"
BLOB_URL = "https://store123.private.blob.vercel-storage.com/demo-sessions/a.db"


def _client(handler, **kwargs) -> VercelBlobClient:
    return VercelBlobClient(TOKEN, transport=httpx.MockTransport(handler), **kwargs)


class TestTokenParsing:
    """Tests for extracting the store id from a read-write token."""

    def test_extracts_fourth_underscore_segment(self):
        """Verify the store id is the segment after ``vercel_blob_rw``."""
        assert parse_store_id(TOKEN) == "store123"

    def test_malformed_token_yields_empty_store_id(self):
        """Verify a token without enough segments does not raise."""
        assert parse_store_id("nonsense") == ""


class TestFromEnv:
    """Tests for building a client from the environment."""

    def test_returns_none_without_token(self, monkeypatch):
        """Verify a deployment without Blob configured gets no client."""
        monkeypatch.delenv(vercel_blob.TOKEN_ENV, raising=False)
        assert VercelBlobClient.from_env() is None

    def test_builds_client_from_token(self, monkeypatch):
        """Verify the env token is picked up and parsed."""
        monkeypatch.setenv(vercel_blob.TOKEN_ENV, TOKEN)
        client = VercelBlobClient.from_env()
        assert client is not None
        assert client.store_id == "store123"

    def test_rejects_unknown_access_mode(self):
        """Verify a typo in the access mode fails loudly at construction."""
        with pytest.raises(ValueError):
            VercelBlobClient(TOKEN, access="secret")


class TestUrlFor:
    """Tests for the blob URL layout."""

    def test_private_and_public_hosts(self):
        """Verify the host encodes store id and access mode like the SDK."""

        def handler(request):  # pragma: no cover - never called
            raise AssertionError

        assert _client(handler).url_for("demo-sessions/a.db") == BLOB_URL
        assert (
            _client(handler, access="public").url_for("x.db")
            == "https://store123.public.blob.vercel-storage.com/x.db"
        )


class TestPut:
    """Tests for uploads."""

    def test_sends_overwriting_put_with_sdk_headers(self):
        """Verify the upload targets ``/?pathname=`` with the SDK's headers."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["body"] = request.content
            return httpx.Response(200, json={"url": BLOB_URL, "etag": '"v1"'})

        result = _client(handler).put("demo-sessions/a.db", b"sqlite")

        assert result.url == BLOB_URL
        assert result.etag == '"v1"'
        assert seen["method"] == "PUT"
        assert seen["url"] == "https://vercel.com/api/blob/?pathname=demo-sessions%2Fa.db"
        assert seen["body"] == b"sqlite"
        headers = seen["headers"]
        assert headers["authorization"] == f"Bearer {TOKEN}"
        assert headers["x-api-version"] == API_VERSION
        assert headers["x-vercel-blob-store-id"] == "store123"
        assert headers["x-vercel-blob-access"] == "private"
        assert headers["x-allow-overwrite"] == "1"
        assert headers["x-add-random-suffix"] == "0"

    def test_learns_real_access_mode_from_returned_url(self):
        """Verify a store created public corrects a client configured private.

        Downloads build the URL from the access mode, so a mismatch would
        make every restore 404 while uploads kept succeeding — silent
        non-persistence. The upload response reveals the truth.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"url": "https://store123.public.blob.vercel-storage.com/p/a.db"},
            )

        client = _client(handler)
        client.put("p/a.db", b"x")

        assert client.access == "public"
        assert client.url_for("p/a.db") == "https://store123.public.blob.vercel-storage.com/p/a.db"

    def test_raises_on_api_error(self):
        """Verify a rejected upload surfaces as an exception, not a bad URL."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"code": "forbidden"}})

        with pytest.raises(httpx.HTTPStatusError):
            _client(handler).put("demo-sessions/a.db", b"x")


class TestList:
    """Tests for listings."""

    def test_follows_cursor_pagination(self):
        """Verify every page is fetched and concatenated."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            if "cursor" not in request.url.params:
                return httpx.Response(
                    200,
                    json={"blobs": [{"pathname": "p/1"}], "cursor": "c1", "hasMore": True},
                )
            return httpx.Response(
                200, json={"blobs": [{"pathname": "p/2"}], "hasMore": False}
            )

        blobs = _client(handler).list("p/")

        assert [b["pathname"] for b in blobs] == ["p/1", "p/2"]
        assert calls[0]["prefix"] == "p/"
        assert calls[1]["cursor"] == "c1"


class TestGet:
    """Tests for downloads."""

    def test_downloads_blob_url_bypassing_cache_with_auth(self):
        """Verify the blob's URL is fetched with the token and ``cache=0``."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["inm"] = request.headers.get("if-none-match")
            return httpx.Response(200, content=b"sqlite-bytes", headers={"etag": '"v2"'})

        result = _client(handler).get("demo-sessions/a.db")

        assert result == BlobObject(data=b"sqlite-bytes", etag='"v2"')
        assert seen["url"] == f"{BLOB_URL}?cache=0"
        assert seen["auth"] == f"Bearer {TOKEN}"
        assert seen["inm"] is None

    def test_sends_if_none_match_and_reports_304(self):
        """Verify a held etag is offered and a 304 comes back as not_modified."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["inm"] = request.headers.get("if-none-match")
            return httpx.Response(304)

        result = _client(handler).get("demo-sessions/a.db", if_none_match='"v2"')

        assert seen["inm"] == '"v2"'
        assert result is not None
        assert result.not_modified is True
        assert result.data is None
        assert result.etag == '"v2"'

    def test_returns_none_on_404(self):
        """Verify a pathname the store does not hold yields ``None``."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        assert _client(handler).get("demo-sessions/missing.db") is None

    def test_raises_on_other_errors(self):
        """Verify auth or server failures are not mistaken for 'absent'."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        with pytest.raises(httpx.HTTPStatusError):
            _client(handler).get("demo-sessions/a.db")


class TestDelete:
    """Tests for deletions."""

    def test_posts_urls_as_json(self):
        """Verify deletion hits ``/delete`` with a JSON ``urls`` body."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={})

        _client(handler).delete(["https://a", "https://b"])

        assert seen["method"] == "POST"
        assert seen["url"] == "https://vercel.com/api/blob/delete"
        assert seen["body"] == {"urls": ["https://a", "https://b"]}

    def test_skips_request_for_empty_list(self):
        """Verify nothing is sent when there is nothing to delete."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request expected")

        _client(handler).delete([])


class TestParseUploadedAt:
    """Tests for the ``uploadedAt`` parser used by pruning."""

    def test_parses_iso_with_z_suffix(self):
        """Verify the API's ISO timestamps become aware datetimes."""
        parsed = parse_uploaded_at("2026-09-01T10:00:00.000Z")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.year == 2026

    def test_parses_epoch_milliseconds(self):
        """Verify numeric timestamps are treated as milliseconds."""
        parsed = parse_uploaded_at(1_756_720_000_000)
        assert parsed is not None
        assert parsed.year == 2025

    @pytest.mark.parametrize("value", [None, "not-a-date", object()])
    def test_unparseable_yields_none(self, value):
        """Verify garbage never raises — pruning must not crash on one record."""
        assert parse_uploaded_at(value) is None
