"""Tests for the shared httpx fetch helpers.

Covers the general error-reporting behavior: failed HTTP requests raise an
``httpx.HTTPStatusError`` whose message includes the response body, so every
API-based scraper surfaces the provider's stated failure reason.
"""

import asyncio

import httpx

from scraper.utils import fetch


def _client(handler) -> httpx.AsyncClient:
    """Build an AsyncClient whose requests are served by ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetchErrorBody:
    """fetch_get / fetch_post include the response body in HTTP errors."""

    def test_post_error_includes_body_and_preserves_status(self):
        """A failing POST raises HTTPStatusError carrying the body and status."""

        def handler(_request):
            return httpx.Response(
                503, json={"errorResponse": {"description": "prefix blocked"}}
            )

        async def run():
            client = _client(handler)
            try:
                error = None
                try:
                    await fetch.fetch_post("https://x/y", {"a": 1}, client=client)
                except httpx.HTTPStatusError as e:
                    error = e
                return error
            finally:
                await client.aclose()

        error = asyncio.run(run())
        assert error is not None
        assert error.response.status_code == 503
        assert "503" in str(error)
        assert "prefix blocked" in str(error)

    def test_get_error_includes_body(self):
        """A failing GET raises HTTPStatusError carrying the response body."""

        def handler(_request):
            return httpx.Response(500, text="boom detail")

        async def run():
            client = _client(handler)
            try:
                error = None
                try:
                    await fetch.fetch_get("https://x/y", client=client)
                except httpx.HTTPStatusError as e:
                    error = e
                return str(error)
            finally:
                await client.aclose()

        msg = asyncio.run(run())
        assert "500" in msg
        assert "boom detail" in msg

    def test_long_body_is_truncated(self):
        """A long error body is truncated so logs stay readable."""

        def handler(_request):
            return httpx.Response(500, text="A" * 1000)

        async def run():
            client = _client(handler)
            try:
                error = None
                try:
                    await fetch.fetch_post("https://x/y", {}, client=client)
                except httpx.HTTPStatusError as e:
                    error = e
                return str(error)
            finally:
                await client.aclose()

        msg = asyncio.run(run())
        assert "…" in msg

    def test_success_returns_parsed_json(self):
        """A 2xx response returns parsed JSON unchanged (no error path)."""

        def handler(_request):
            return httpx.Response(200, json={"ok": True})

        async def run():
            client = _client(handler)
            try:
                return await fetch.fetch_post("https://x/y", {}, client=client)
            finally:
                await client.aclose()

        assert asyncio.run(run()) == {"ok": True}
