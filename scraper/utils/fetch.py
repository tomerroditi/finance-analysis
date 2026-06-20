import json
import logging
from typing import Any, Optional

import httpx
from playwright.async_api import Page

from scraper.exceptions import ErrorType, ScraperError

logger = logging.getLogger(__name__)

JSON_CONTENT_TYPE = "application/json"


def _json_headers() -> dict[str, str]:
    return {"Accept": JSON_CONTENT_TYPE, "Content-Type": JSON_CONTENT_TYPE}


def _raise_for_status_with_body(resp: httpx.Response) -> None:
    """Like ``resp.raise_for_status()`` but include the response body in the error.

    httpx's default ``HTTPStatusError`` message contains only the status line and
    URL; the response body — where providers explain *why* a request failed
    (rate-limit notices, validation messages, blocked-number reasons) — is
    dropped. This re-raises the same ``HTTPStatusError`` with the status code and
    response preserved (so status-based handling such as retry logic still
    works) and a message that appends a truncated body.

    Parameters
    ----------
    resp : httpx.Response
        The response to validate.

    Raises
    ------
    httpx.HTTPStatusError
        If the status indicates an error, with the body included in the message.
    """
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as error:
        body = (resp.text or "").strip()
        if len(body) > 500:
            body = body[:500] + "…"
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code} {resp.request.url} — body: {body or '<empty>'}",
            request=error.request,
            response=error.response,
        ) from error


async def fetch_get(
    url: str,
    extra_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """HTTP GET returning parsed JSON. Uses httpx (no browser)."""
    headers = {**_json_headers(), **(extra_headers or {})}
    _client = client or httpx.AsyncClient()
    try:
        resp = await _client.get(url, headers=headers)
        _raise_for_status_with_body(resp)
        return resp.json()
    finally:
        if not client:
            await _client.aclose()


async def fetch_post(
    url: str,
    data: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """HTTP POST returning parsed JSON. Uses httpx (no browser)."""
    headers = {**_json_headers(), **(extra_headers or {})}
    _client = client or httpx.AsyncClient()
    try:
        resp = await _client.post(url, json=data, headers=headers)
        _raise_for_status_with_body(resp)
        return resp.json()
    finally:
        if not client:
            await _client.aclose()


async def fetch_graphql(
    url: str,
    query: str,
    variables: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """GraphQL query via HTTP POST. Returns the `data` field."""
    payload = {"operationName": None, "query": query, "variables": variables or {}}
    result = await fetch_post(url, payload, extra_headers, client)
    if result.get("errors"):
        raise ScraperError(result["errors"][0]["message"], ErrorType.GENERIC)
    return result["data"]


async def fetch_get_within_page(
    page: Page, url: str, ignore_errors: bool = False
) -> Optional[Any]:
    """Execute fetch() GET inside the browser page context. Inherits session cookies."""
    js_fn = """async (url) => {
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (response.status === 204) return { __data: null, __status: 204 };
                const text = await response.text();
                return { __data: text, __status: response.status };
            } catch (e) {
                return { __error: e.message, __status: 0 };
            }
        }"""
    result = await page.evaluate(js_fn, url)
    if "__error" in result:
        if not ignore_errors:
            raise ScraperError(
                f"fetchGetWithinPage error: {result['__error']}, url: {url}",
                ErrorType.GENERIC,
            )
        return None
    data = result.get("__data")
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        if not ignore_errors:
            raise ScraperError(
                f"fetchGetWithinPage parse error: {e}, url: {url}, status: {result.get('__status')}",
                ErrorType.GENERIC,
            )
        return None


async def fetch_post_within_page(
    page: Page,
    url: str,
    data: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
    ignore_errors: bool = False,
) -> Optional[Any]:
    """Execute fetch() POST inside the browser page context. Inherits session cookies."""
    js_fn = """async ([url, data, extraHeaders]) => {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: JSON.stringify(data),
                    credentials: 'include',
                    headers: Object.assign(
                        { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                        extraHeaders
                    ),
                });
                if (response.status === 204) return { __data: null };
                return { __data: await response.text() };
            } catch (e) {
                return { __error: e.message };
            }
        }"""
    result = await page.evaluate(js_fn, [url, data, extra_headers or {}])
    if "__error" in result:
        if not ignore_errors:
            raise ScraperError(
                f"fetchPostWithinPage error: {result['__error']}, url: {url}",
                ErrorType.GENERIC,
            )
        return None
    text = result.get("__data")
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if not ignore_errors:
            raise ScraperError(
                f"fetchPostWithinPage parse error: {e}, url: {url}",
                ErrorType.GENERIC,
            )
        return None
