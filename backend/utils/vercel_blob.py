"""Minimal Vercel Blob client over the public REST contract.

Vercel ships no Python SDK for Blob, so this module speaks the same HTTP the
official ``@vercel/blob`` package does: uploads and listings go through
``https://vercel.com/api/blob`` with the read-write token as a bearer, and
downloads fetch the blob's own URL with that token (required for private
stores, harmless for public ones). Only the four operations the per-visitor
demo sandboxes need are implemented — put, get, delete, list.
"""

from __future__ import annotations

import logging
import os
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


class BlobBackend(Protocol):
    """The subset of blob operations :mod:`backend.demo_sessions` relies on."""

    def put(self, pathname: str, data: bytes) -> str:
        """Upload ``data`` under ``pathname`` and return the blob URL."""

    def get(self, pathname: str) -> bytes | None:
        """Return the bytes stored under ``pathname``, or ``None`` if absent."""

    def delete(self, urls: list[str]) -> None:
        """Delete every blob in ``urls``. Unknown URLs are ignored."""

    def list(self, prefix: str) -> list[dict]:
        """Return metadata (``url``, ``pathname``, ``uploadedAt``) under ``prefix``."""


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
        ``"private"`` (default) or ``"public"`` — must match the store.
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
        self._access = access
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
            instance-local storage rather than failing.
        """
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            return None
        access = os.environ.get("FAD_DEMO_BLOB_ACCESS", "private").strip() or "private"
        return cls(token, access=access)

    def _api_headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._token}",
            "x-api-version": API_VERSION,
            "x-vercel-blob-store-id": self.store_id,
        }

    def put(self, pathname: str, data: bytes) -> str:
        """Upload ``data`` to ``pathname``, overwriting any existing blob.

        Parameters
        ----------
        pathname : str
            Blob pathname (no leading slash).
        data : bytes
            File contents.

        Returns
        -------
        str
            The blob's URL as reported by the API.
        """
        response = self._client.put(
            f"{self._api_url}/",
            params={"pathname": pathname},
            content=data,
            headers={
                **self._api_headers(),
                "x-vercel-blob-access": self._access,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-content-type": "application/octet-stream",
                "x-cache-control-max-age": str(MIN_CACHE_MAX_AGE),
            },
        )
        response.raise_for_status()
        return response.json()["url"]

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

    def get(self, pathname: str) -> bytes | None:
        """Download the blob stored at ``pathname``.

        The blob URL comes from a listing rather than being constructed, so
        the host is right whichever access mode the store was created with.
        ``cache=0`` bypasses the CDN so a freshly re-uploaded pathname is
        never served stale.

        Parameters
        ----------
        pathname : str
            Blob pathname.

        Returns
        -------
        bytes | None
            The contents, or ``None`` when no such blob exists.
        """
        match = next(
            (b for b in self.list(pathname) if b.get("pathname") == pathname), None
        )
        if match is None:
            return None
        response = self._client.get(
            match["url"],
            params={"cache": "0"},
            headers={"authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    def delete(self, urls: list[str]) -> None:
        """Delete the blobs at ``urls``.

        Parameters
        ----------
        urls : list[str]
            Blob URLs (as returned by :meth:`put` / :meth:`list`).
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
