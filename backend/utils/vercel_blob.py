"""Minimal Vercel Blob client over the public REST contract.

Vercel ships no Python SDK for Blob, so this module speaks the same HTTP the
official ``@vercel/blob`` package does: uploads and listings go through
``https://vercel.com/api/blob`` with the read-write token as a bearer, and
downloads fetch the blob's own URL with that token (required for private
stores, harmless for public ones). Only the operations the per-visitor demo
sandboxes need are implemented — put, get (with ``If-None-Match``), delete,
list.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
DEFAULT_API_URL = "https://vercel.com/api/blob"
#: Matches the ``@vercel/blob`` SDK release this client was written against.
API_VERSION = "12"
#: Smallest cache lifetime the Blob API accepts. Downloads add ``cache=0``
#: anyway, so this only bounds how stale a CDN edge may serve a re-uploaded
#: pathname to a reader that bypasses this client.
MIN_CACHE_MAX_AGE = 60

_BLOB_HOST_RE = re.compile(r"^([^.]+)\.(public|private)\.blob\.vercel-storage\.com$")


@dataclass(frozen=True)
class BlobPutResult:
    """What an upload reports back: where the blob lives and its version."""

    url: str
    etag: str | None


@dataclass(frozen=True)
class BlobObject:
    """A download result.

    ``not_modified`` is set when the server answered 304 to an
    ``If-None-Match`` — ``data`` is then ``None`` and ``etag`` echoes the
    caller's. Otherwise ``data`` holds the bytes and ``etag`` their version.
    """

    data: bytes | None
    etag: str | None
    not_modified: bool = False


class BlobBackend(Protocol):
    """The subset of blob operations :mod:`backend.demo_sessions` relies on."""

    def put(self, pathname: str, data: bytes) -> BlobPutResult:
        """Upload ``data`` under ``pathname``, overwriting any previous version."""

    def get(self, pathname: str, if_none_match: str | None = None) -> BlobObject | None:
        """Fetch ``pathname``; ``None`` if absent, ``not_modified`` on an etag hit."""

    def delete(self, urls: list[str]) -> None:
        """Delete every blob in ``urls``. Unknown URLs are ignored."""

    def list(self, prefix: str) -> list[dict]:
        """Return metadata (``url``, ``pathname``, ``uploadedAt``) under ``prefix``."""

    def url_for(self, pathname: str) -> str:
        """Return the URL a blob at ``pathname`` is served from."""


def parse_store_id(token: str) -> str:
    """Extract the store id from a ``vercel_blob_rw_<store>_<secret>`` token.

    Parameters
    ----------
    token : str
        A Blob read-write token.

    Returns
    -------
    str
        The store id segment, or an empty string when the token is malformed.
    """
    parts = token.split("_")
    return parts[3] if len(parts) > 3 else ""


class VercelBlobClient:
    """Synchronous Vercel Blob client backed by :mod:`httpx`.

    Parameters
    ----------
    token : str
        Blob read-write token (``BLOB_READ_WRITE_TOKEN``).
    access : str
        ``"private"`` (default) or ``"public"``. Should match the store; if
        it does not, the first successful upload reveals the real mode from
        the returned URL and the client corrects itself.
    api_url : str, optional
        Override of the Blob API base URL (tests, proxies).
    transport : httpx.BaseTransport, optional
        Injected transport, used by tests to stub the network.
    timeout : float
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        token: str,
        *,
        access: str = "private",
        api_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        if access not in ("private", "public"):
            raise ValueError(f"access must be 'private' or 'public', got {access!r}")
        self._token = token
        self.access = access
        self._api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self.store_id = parse_store_id(token)
        self._client = httpx.Client(transport=transport, timeout=timeout)

    @classmethod
    def from_env(cls) -> VercelBlobClient | None:
        """Build a client from ``BLOB_READ_WRITE_TOKEN``, or ``None`` if unset.

        Returns
        -------
        VercelBlobClient | None
            ``None`` means "no remote persistence" — callers fall back to
            instance-local storage rather than failing. Returned both when
            the variable is unset and when its value carries no store id,
            since such a token can never address a blob.
        """
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            return None
        if not parse_store_id(token):
            # Downloads address the store by id, so a token we cannot parse
            # yields a client that can never read a blob back. Report it as
            # "no Blob store" instead: the cold-start warning and
            # ``blob_configured`` then say so, rather than advertising
            # durability the deployment does not have.
            logger.warning(
                "%s is set but carries no store id; demo sandboxes will not "
                "be durable. Re-connect the Blob store to the project.",
                TOKEN_ENV,
            )
            return None
        access = os.environ.get("FAD_DEMO_BLOB_ACCESS", "private").strip() or "private"
        return cls(token, access=access)

    def url_for(self, pathname: str) -> str:
        """Return the URL a blob at ``pathname`` is served from.

        Mirrors the SDK's ``constructBlobUrl``: the host encodes the store id
        and the access mode.
        """
        return f"https://{self.store_id}.{self.access}.blob.vercel-storage.com/{pathname}"

    def _learn_access_from_url(self, url: str) -> None:
        """Adopt the access mode the server reports, if it differs from ours."""
        try:
            host = httpx.URL(url).host
        except (httpx.InvalidURL, TypeError, ValueError):
            return
        match = _BLOB_HOST_RE.match(host or "")
        if match and match.group(2) != self.access:
            logger.warning(
                "Blob store is %s but client was configured %s; switching",
                match.group(2),
                self.access,
            )
            self.access = match.group(2)

    def _api_headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._token}",
            "x-api-version": API_VERSION,
            "x-vercel-blob-store-id": self.store_id,
        }

    def put(self, pathname: str, data: bytes) -> BlobPutResult:
        """Upload ``data`` to ``pathname``, overwriting any existing blob.

        Parameters
        ----------
        pathname : str
            Blob pathname (no leading slash).
        data : bytes
            File contents.

        Returns
        -------
        BlobPutResult
            The blob's URL and the etag of the version just written.
        """
        response = self._client.put(
            f"{self._api_url}/",
            params={"pathname": pathname},
            content=data,
            headers={
                **self._api_headers(),
                "x-vercel-blob-access": self.access,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-content-type": "application/octet-stream",
                "x-cache-control-max-age": str(MIN_CACHE_MAX_AGE),
            },
        )
        response.raise_for_status()
        payload = response.json()
        url = payload["url"]
        self._learn_access_from_url(url)
        return BlobPutResult(url=url, etag=payload.get("etag"))

    def list(self, prefix: str) -> list[dict]:
        """List every blob whose pathname starts with ``prefix``.

        Parameters
        ----------
        prefix : str
            Pathname prefix to filter on.

        Returns
        -------
        list[dict]
            Raw blob records (``url``, ``pathname``, ``size``, ``uploadedAt``).
        """
        blobs: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict[str, str] = {"prefix": prefix, "limit": "1000"}
            if cursor:
                params["cursor"] = cursor
            response = self._client.get(
                f"{self._api_url}/", params=params, headers=self._api_headers()
            )
            response.raise_for_status()
            payload = response.json()
            blobs.extend(payload.get("blobs", []))
            cursor = payload.get("cursor")
            if not payload.get("hasMore") or not cursor:
                return blobs

    def get(self, pathname: str, if_none_match: str | None = None) -> BlobObject | None:
        """Download the blob stored at ``pathname``.

        ``cache=0`` bypasses the CDN so a freshly re-uploaded pathname is
        never served stale; ``If-None-Match`` lets a caller that already
        holds a version pay only for a 304 when nothing changed.

        Parameters
        ----------
        pathname : str
            Blob pathname.
        if_none_match : str, optional
            Etag the caller already has.

        Returns
        -------
        BlobObject | None
            ``None`` when no such blob exists.
        """
        headers = {"authorization": f"Bearer {self._token}"}
        if if_none_match:
            headers["if-none-match"] = if_none_match
        response = self._client.get(
            self.url_for(pathname), params={"cache": "0"}, headers=headers
        )
        if response.status_code == 404:
            return None
        if response.status_code == 304:
            return BlobObject(data=None, etag=if_none_match, not_modified=True)
        response.raise_for_status()
        return BlobObject(data=response.content, etag=response.headers.get("etag"))

    def delete(self, urls: list[str]) -> None:
        """Delete the blobs at ``urls``.

        Parameters
        ----------
        urls : list[str]
            Blob URLs (as returned by :meth:`put` / :meth:`list` / :meth:`url_for`).
        """
        if not urls:
            return
        response = self._client.post(
            f"{self._api_url}/delete",
            json={"urls": urls},
            headers={**self._api_headers(), "content-type": "application/json"},
        )
        response.raise_for_status()


def parse_uploaded_at(value: str | float | None) -> datetime | None:
    """Parse the ``uploadedAt`` field of a blob record.

    Parameters
    ----------
    value : str | float | None
        ISO-8601 string (``2026-09-01T10:00:00.000Z``) or epoch milliseconds.

    Returns
    -------
    datetime | None
        Timezone-aware datetime, or ``None`` when unparseable.
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OSError):
        return None
