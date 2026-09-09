"""Per-visitor demo sandboxes for the shared serverless deployment.

The Vercel demo used to be one SQLite file in ``/tmp``: every visitor wrote
to the same copy and every cold start threw it away. This module gives each
browser its own copy — keyed by the ``X-FAD-Demo-Session`` header, a random
id the frontend mints once and keeps in localStorage — and mirrors that copy
to Vercel Blob after every successful write, so the sandbox survives
instance recycling and follows the visitor across instances.

The whole database file is the unit of persistence (it is ~1.3 MB), which
keeps the backend SQLite-only: no second dialect, no per-row sync. Cost per
write request is one upload; a session's first request on a fresh instance
is one download, or a copy of the pristine template when nothing is stored.

Nothing here is active unless ``FAD_DEMO_SESSIONS=1`` — the local app and
the e2e suite keep the single shared demo database.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend import database
from backend.config import AppConfig
from backend.utils.vercel_blob import (
    BlobBackend,
    VercelBlobClient,
    parse_uploaded_at,
)

logger = logging.getLogger(__name__)

SESSION_HEADER = "X-FAD-Demo-Session"
SESSIONS_ENV = "FAD_DEMO_SESSIONS"
TTL_ENV = "FAD_DEMO_SESSION_TTL_DAYS"
DEFAULT_TTL_DAYS = 14
#: Blob pathname prefix for persisted sandboxes: ``demo-sessions/<id>.db``.
BLOB_PREFIX = "demo-sessions/"
#: Pristine, date-shifted copy of the demo DB that new sandboxes are cloned
#: from. Lives beside the shared demo DB; written once per cold start.
TEMPLATE_FILENAME = "demo_template.db"

#: Path-safe, unguessable, and long enough that a client cannot collide with
#: another visitor by accident. UUIDs (with or without dashes) fit.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def sessions_enabled() -> bool:
    """Return whether per-visitor demo sandboxes are switched on."""
    return os.environ.get(SESSIONS_ENV) == "1"


def parse_session_id(raw: str | None) -> str | None:
    """Validate a client-supplied sandbox id.

    Parameters
    ----------
    raw : str | None
        Value of the ``X-FAD-Demo-Session`` header.

    Returns
    -------
    str | None
        The id when well-formed, else ``None`` (treated as "no sandbox").
    """
    if not raw:
        return None
    value = raw.strip()
    return value if _SESSION_ID_RE.fullmatch(value) else None


def blob_pathname(session_id: str) -> str:
    """Return the Blob pathname a sandbox is persisted under."""
    return f"{BLOB_PREFIX}{session_id}.db"


def _sidecar_paths(db_path: str) -> list[str]:
    """SQLite journal files that must be removed together with ``db_path``."""
    return [f"{db_path}-journal", f"{db_path}-wal", f"{db_path}-shm"]


def _forget_database(db_path: str) -> None:
    """Drop everything the process remembers about a replaced DB file.

    The engine registry and the module-level categories/credentials caches
    are all partitioned by path; a sandbox that was restored, re-seeded or
    wiped must not be served from state belonging to the previous file.
    """
    database.reset_engine_for(db_path)
    from backend.services.tagging_service import CategoriesTagsService

    CategoriesTagsService.clear_cache_for(db_path)
    try:
        from backend.services.credentials_service import CredentialsService
    except ImportError:
        # The Vercel runtime ships no keyring, so credentials_service cannot
        # import there — and then its cache cannot hold anything either.
        return
    CredentialsService.clear_cache_for(db_path)


class DemoSessionStore:
    """Materializes, persists and resets per-visitor demo databases.

    Parameters
    ----------
    backend : BlobBackend | None
        Remote store for sandbox files. ``None`` keeps sandboxes
        instance-local (still isolated per visitor, but not durable).
    """

    def __init__(self, backend: BlobBackend | None) -> None:
        self.backend = backend
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @property
    def durable(self) -> bool:
        """Whether sandboxes outlive the serving instance."""
        return self.backend is not None

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, threading.Lock())

    @staticmethod
    def template_path() -> str:
        """Path of the pristine template new sandboxes are cloned from."""
        return os.path.join(AppConfig().get_demo_root_dir(), TEMPLATE_FILENAME)

    @staticmethod
    def local_db_path(session_id: str) -> str:
        """Resolve the on-disk database path of ``session_id``'s sandbox."""
        config = AppConfig()
        mode_token = config.set_demo_mode(True, ensure_dir=False)
        session_token = config.set_demo_session(session_id)
        try:
            return config.get_db_path()
        finally:
            config.reset_demo_session(session_token)
            config.reset_demo_mode(mode_token)

    def is_ready(self, session_id: str) -> bool:
        """Return whether the sandbox already exists on this instance."""
        return os.path.exists(self.local_db_path(session_id))

    def ensure_local(self, session_id: str) -> None:
        """Make sure the sandbox database exists on this instance.

        Restores the persisted copy when the backend has one, otherwise
        clones the template (or, lacking a template, builds the demo
        database from the frozen snapshot directly into the sandbox).
        """
        path = self.local_db_path(session_id)
        if os.path.exists(path):
            return
        with self._lock_for(session_id):
            if os.path.exists(path):
                return
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = self._download(session_id)
            if data is not None:
                self._write_atomically(path, data)
                logger.info("Restored demo sandbox %s from blob storage", session_id)
                return
            self._seed(session_id, path)

    def _download(self, session_id: str) -> bytes | None:
        if self.backend is None:
            return None
        try:
            return self.backend.get(blob_pathname(session_id))
        except Exception:  # never let a storage hiccup 500 the demo
            logger.warning(
                "Could not fetch demo sandbox %s; seeding a fresh one",
                session_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def _write_atomically(path: str, data: bytes) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        _forget_database(path)

    def _seed(self, session_id: str, path: str) -> None:
        template = self.template_path()
        if os.path.exists(template):
            shutil.copy2(template, path)
            _forget_database(path)
            return
        # No template (local dev / tests): build straight into the sandbox.
        # prepare_demo_database resolves its target through AppConfig, which
        # honours the bound session id.
        from backend.demo_setup import prepare_demo_database

        config = AppConfig()
        session_token = config.set_demo_session(session_id)
        try:
            prepare_demo_database()
        finally:
            config.reset_demo_session(session_token)
        _forget_database(path)

    def persist(self, session_id: str) -> bool:
        """Upload the sandbox database to the backend.

        Returns
        -------
        bool
            ``True`` when an upload happened. Failures are logged, never
            raised — the visitor's request already succeeded locally.
        """
        if self.backend is None:
            return False
        path = self.local_db_path(session_id)
        if not os.path.exists(path):
            return False
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            self.backend.put(blob_pathname(session_id), data)
            return True
        except Exception:
            logger.warning(
                "Could not persist demo sandbox %s", session_id, exc_info=True
            )
            return False

    def reset(self, session_id: str) -> None:
        """Discard the sandbox everywhere and re-seed it from the template.

        The caller's request is mutating, so the request middleware uploads
        the fresh copy afterwards; this method does not persist itself.
        """
        path = self.local_db_path(session_id)
        with self._lock_for(session_id):
            _forget_database(path)
            for stale in [path, *_sidecar_paths(path)]:
                if os.path.exists(stale):
                    os.remove(stale)
            if self.backend is not None:
                try:
                    urls = [
                        b["url"]
                        for b in self.backend.list(blob_pathname(session_id))
                        if b.get("pathname") == blob_pathname(session_id)
                    ]
                    self.backend.delete(urls)
                except Exception:
                    logger.warning(
                        "Could not delete persisted demo sandbox %s",
                        session_id,
                        exc_info=True,
                    )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._seed(session_id, path)

    def prune(self, max_age_days: int | None = None) -> int:
        """Delete persisted sandboxes not written to for ``max_age_days``.

        Parameters
        ----------
        max_age_days : int, optional
            Age threshold; defaults to ``FAD_DEMO_SESSION_TTL_DAYS`` or 14.

        Returns
        -------
        int
            Number of blobs deleted.
        """
        if self.backend is None:
            return 0
        if max_age_days is None:
            max_age_days = int(os.environ.get(TTL_ENV, DEFAULT_TTL_DAYS))
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        stale = []
        for blob in self.backend.list(BLOB_PREFIX):
            uploaded = parse_uploaded_at(blob.get("uploadedAt"))
            if uploaded is not None and uploaded < cutoff:
                stale.append(blob["url"])
        self.backend.delete(stale)
        return len(stale)


_store: DemoSessionStore | None = None
_store_guard = threading.Lock()


def get_store() -> DemoSessionStore:
    """Return the process-wide store, building it from the environment once."""
    global _store
    with _store_guard:
        if _store is None:
            _store = DemoSessionStore(VercelBlobClient.from_env())
        return _store


def set_store(store: DemoSessionStore | None) -> None:
    """Replace the process-wide store (tests, custom backends)."""
    global _store
    with _store_guard:
        _store = store


def snapshot_template() -> None:
    """Freeze the current shared demo database as the sandbox template.

    Call once right after the shared demo DB has been prepared and before
    any request is served, so every sandbox starts from the same pristine,
    date-shifted data regardless of what later happens to the shared copy.
    """
    config = AppConfig()
    mode_token = config.set_demo_mode(True)
    session_token = config.set_demo_session(None)
    try:
        source = config.get_db_path()
    finally:
        config.reset_demo_session(session_token)
        config.reset_demo_mode(mode_token)
    if os.path.exists(source):
        shutil.copy2(source, DemoSessionStore.template_path())


async def serve_in_session(request: Request, call_next, session_id: str) -> Response:
    """Run ``request`` against ``session_id``'s sandbox and persist writes.

    Binds the sandbox id for the request's context, materializes the
    database first if this instance has not seen the visitor yet, and — for
    a successful mutating ``/api`` request — uploads the file afterwards.
    Blocking file and network work runs in the threadpool so the event loop
    stays free.
    """
    store = get_store()
    config = AppConfig()
    token = config.set_demo_session(session_id)
    try:
        if not store.is_ready(session_id):
            try:
                await run_in_threadpool(store.ensure_local, session_id)
            except Exception:
                logger.exception("Could not materialize demo sandbox %s", session_id)
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Demo sandbox is temporarily unavailable"},
                )
        response = await call_next(request)
        if (
            request.method in _MUTATING_METHODS
            and request.url.path.startswith("/api/")
            and 200 <= response.status_code < 400
        ):
            await run_in_threadpool(store.persist, session_id)
        return response
    finally:
        config.reset_demo_session(token)
