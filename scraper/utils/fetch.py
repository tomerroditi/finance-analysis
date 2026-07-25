import json
import logging
import re
from typing import Any, Optional

import httpx
from playwright.async_api import Page

from scraper.exceptions import AutomationBlockedError, ErrorType, ScraperError

logger = logging.getLogger(__name__)

JSON_CONTENT_TYPE = "application/json"

_AUTOMATION_BLOCKED_PATTERN = re.compile(r"block automation|bot detection", re.IGNORECASE)

# Text a WAF interstitial serves in place of the API's own response body.
_WAF_BODY_PATTERN = re.compile(
    r"cf-browser-verification|cf_chl_opt|/cdn-cgi/challenge-platform"
    r"|attention required|checking your browser|just a moment"
    r"|access denied|request blocked|akamai",
    re.IGNORECASE,
)

# Response headers only an edge/WAF sets, never the origin API.
_WAF_HEADERS = ("cf-ray", "cf-mitigated", "x-akamai-request-id")

_REMEDIATION = (
    "The site is actively blocking automated access. Consider: "
    "1) Using show_browser=True, 2) Adding longer delays, "
    "3) Using residential proxies, 4) Running at different times of day"
)


def _json_headers() -> dict[str, str]:
    return {"Accept": JSON_CONTENT_TYPE, "Content-Type": JSON_CONTENT_TYPE}


def _assert_automation_not_blocked(
    status: Optional[int], response_text: Optional[str], url: str
) -> None:
    """Raise when the provider answered with an anti-automation block.

    Providers that detect a headless browser answer with `429 Too Many
    Requests` or a body naming the detector rather than an error status. Both
    parse as "no data" downstream, so surface them as an explicit error with
    remediation hints instead of an opaque JSON parse failure.

    Parameters
    ----------
    status : Optional[int]
        HTTP status code of the in-page fetch.
    response_text : Optional[str]
        Raw response body, if any.
    url : str
        The requested URL, included in the error message.

    Raises
    ------
    AutomationBlockedError
        If the response looks like an anti-automation block.
    """
    blocked_body = bool(response_text and _AUTOMATION_BLOCKED_PATTERN.search(response_text))
    if status == 429 or blocked_body:
        raise AutomationBlockedError(
            f"Automation detected and blocked by server. Status: {status}, "
            f"URL: {url}. {_REMEDIATION}"
        )


def _describe_waf_evidence(resp: httpx.Response) -> Optional[str]:
    """Return why a response looks like a WAF block, or None if it doesn't.

    Distinguishes an edge rejection from a genuine API error. Both can be a
    403, so status alone proves nothing — the tell is either a header only an
    edge sets, or challenge markup where JSON was expected. Requiring one of
    those keeps a legitimate ``403 {"error": "forbidden"}`` from the origin out
    of the automation-blocked bucket.

    Parameters
    ----------
    resp : httpx.Response
        The failing response.

    Returns
    -------
    Optional[str]
        A short description of the evidence found, or None when the response
        carries no WAF signal.
    """
    if resp.status_code == 429:
        return "status 429"

    if resp.status_code not in (401, 403, 503):
        return None

    edge_headers = [h for h in _WAF_HEADERS if h in resp.headers]
    try:
        body = resp.text or ""
    except Exception:
        body = ""
    body_match = _WAF_BODY_PATTERN.search(body)

    # An edge header alone is not proof — Cloudflare fronts plenty of APIs and
    # stamps cf-ray on their legitimate errors too. Pair it with a body that
    # isn't the API's own JSON.
    looks_like_html = body.lstrip()[:1] == "<"
    if body_match:
        return f"challenge markup ({body_match.group(0)!r})"
    if edge_headers and looks_like_html:
        return f"edge headers {edge_headers} with an HTML body"
    return None


def _raise_for_status_with_body(resp: httpx.Response) -> None:
    """Like ``resp.raise_for_status()`` but include the response body in the error.

    httpx's default ``HTTPStatusError`` message contains only the status line and
    URL; the response body — where providers explain *why* a request failed
    (rate-limit notices, validation messages, blocked-number reasons) — is
    dropped. This re-raises the same ``HTTPStatusError`` with the status code and
    response preserved (so status-based handling such as retry logic still
    works) and a message that appends a truncated body.

    The one exception is a WAF block, which is raised as ``AutomationBlockedError``
    so it lands in the scrape history under its own error type instead of the
    ``GENERAL_ERROR`` bucket. That trades away ``HTTPStatusError`` for those
    responses — deliberately: the status-based handlers that matter here key on
    markers a challenge page never carries (One Zero's Twilio block is a 503
    with an ``ErrorOtpService`` body), so none of them can match a WAF response
    anyway.

    Parameters
    ----------
    resp : httpx.Response
        The response to validate.

    Raises
    ------
    AutomationBlockedError
        If the failure carries WAF evidence (edge headers, challenge markup).
    httpx.HTTPStatusError
        For every other error status, with the body included in the message.
    """
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as error:
        evidence = _describe_waf_evidence(resp)
        if evidence is not None:
            raise AutomationBlockedError(
                f"Blocked before reaching the provider ({evidence}). "
                f"Status: {resp.status_code}, URL: {resp.request.url}. {_REMEDIATION}"
            ) from error

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
    if not ignore_errors:
        _assert_automation_not_blocked(result.get("__status"), result.get("__data"), url)
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
                if (response.status === 204) return { __data: null, __status: 204 };
                return { __data: await response.text(), __status: response.status };
            } catch (e) {
                return { __error: e.message, __status: 0 };
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
    if not ignore_errors:
        _assert_automation_not_blocked(result.get("__status"), result.get("__data"), url)
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
