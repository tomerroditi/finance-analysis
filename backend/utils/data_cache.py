"""Process-wide cache for expensive derived reads, versioned by write activity.

``session_cache`` collapses repeated full-table reads *within* one request.
That is not enough for the dashboard: it fires ~25 independent requests, each
with its own session, and several of them recompute the identical thing. The
recurring-charge detection alone ran five times per dashboard load (once for
``/analytics/recurring``, once inside the forecast, twice inside the insights
strip, once for the budget overview) at ~1.2 s a run.

This module caches such results across requests and invalidates them the
moment the data underneath could have changed.

Invalidation
------------
Each database gets one *generation*, tagged with a version token that changes
whenever the file might have been written:

* **In-process writes** bump a global counter from the same
  ``Session.after_commit`` / ``after_rollback`` listeners that already clear
  ``session_cache``. Every repository write method commits immediately, so a
  committed change is visible to the very next lookup.
* **Out-of-process writes** (a second dev server on the same file, a restore
  that swaps the file) are caught by the database file's ``(size, mtime_ns)``.
  SQLite in rollback-journal mode — the mode this app runs in — writes the
  main file on commit, so a foreign commit moves one or both.

The version is deliberately coarse: *any* commit discards the whole
generation, including entries the write could not have affected. That is the
safe direction, and it costs nothing in practice because reads do not commit
— the only write-on-read paths (savings-goal allocation persistence, budget
seeding) are idempotent and settle after their first call. Discarding whole
generations is also what bounds memory: at most one generation per database
is ever held.

A session with pending ORM state is never served from — or written to — the
cache, so a caller mid-transaction cannot publish its uncommitted view to
other threads.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Hashable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

_Version = tuple[int, int, int]

#: Bumped on every commit/rollback anywhere in the process.
_write_counter = 0

#: ``db_path -> (version, {key: value})``. One generation per database.
_generations: dict[str, tuple[_Version, dict[tuple[Hashable, ...], Any]]] = {}

#: One lock per cache key, so concurrent misses collapse into one
#: computation (see ``_single_flight_lock``).
_key_locks: dict[tuple[Hashable, ...], threading.Lock] = {}

_lock = threading.Lock()


def _db_path(db: Session) -> str:
    """Filesystem path of the database a session is bound to.

    Parameters
    ----------
    db : Session
        The session whose bind to inspect.

    Returns
    -------
    str
        The resolved database path, or ``""`` when the session is not backed
        by a file. ``""`` disables caching for that session — an in-memory
        database has no file identity, so every such session would otherwise
        share one bucket and read entries built from a different database's
        rows. Production always resolves to a real path; in-memory databases
        are a test-only construct, and small enough that not caching them
        costs nothing.
    """
    bind = db.get_bind()
    database = getattr(getattr(bind, "url", None), "database", None)
    if not database or database == ":memory:":
        return ""
    return database


def _version(path: str) -> _Version:
    """Build the invalidation token for a database path.

    Parameters
    ----------
    path : str
        Filesystem path of the database.

    Returns
    -------
    tuple
        ``(write_counter, size, mtime_ns)``. Comparing this against a stored
        token answers "could the data have changed since?".
    """
    with _lock:
        counter = _write_counter
    try:
        stat = os.stat(path)
        fingerprint = (stat.st_size, stat.st_mtime_ns)
    except OSError:
        # No file to stat (in-memory DB, or it was just swapped out). The
        # write counter still versions in-process changes.
        fingerprint = (-1, -1)
    return (counter, *fingerprint)


def _has_pending_state(db: Session) -> bool:
    """Whether the session holds uncommitted ORM changes.

    Parameters
    ----------
    db : Session
        The session to inspect.

    Returns
    -------
    bool
        True when the session has new, dirty, or deleted instances — in which
        case its reads reflect a view no other session can see yet.
    """
    return bool(db.new or db.dirty or db.deleted)


def _single_flight_lock(full_key: tuple[Hashable, ...]) -> threading.Lock:
    """Return the lock guarding one key's computation.

    Parameters
    ----------
    full_key : tuple
        Database-qualified cache key.

    Returns
    -------
    threading.Lock
        A lock unique to ``full_key``, created on first use. Locks are kept
        for the process's lifetime — there is a fixed, small set of keys, so
        this cannot grow without bound.
    """
    with _lock:
        return _key_locks.setdefault(full_key, threading.Lock())


def _lookup(
    path: str, version: _Version, key: tuple[Hashable, ...]
) -> tuple[bool, Any]:
    """Read one entry, if the stored generation still matches.

    Parameters
    ----------
    path : str
        Database path.
    version : tuple
        The version the caller considers current.
    key : tuple
        Cache key within the generation.

    Returns
    -------
    tuple
        ``(hit, value)`` — ``value`` is meaningless when ``hit`` is False.
        A sentinel-free two-tuple so that a legitimately cached ``None``
        still reads as a hit.
    """
    with _lock:
        generation = _generations.get(path)
        if generation is not None and generation[0] == version and key in generation[1]:
            return True, generation[1][key]
    return False, None


def cached[T](db: Session, key: tuple[Hashable, ...], compute: Callable[[], T]) -> T:
    """Return ``compute()``'s result, reusing it across requests when valid.

    Parameters
    ----------
    db : Session
        The request's session. Supplies the database identity and the
        pending-state check; it is not stored.
    key : tuple
        Hashable cache key, namespaced by the caller (e.g.
        ``("recurring.get_recurring", today, include_dismissed)``). Entries
        are held per database, so demo and real mode never share one.
    compute : callable
        Zero-argument callable producing the value on a miss. Must be pure
        with respect to ``key`` — it is skipped entirely on a hit.

    Returns
    -------
    T
        The cached or freshly computed value. Callers that mutate the result
        must copy it first; nothing is copied on their behalf.
    """
    path = _db_path(db)
    if not path or _has_pending_state(db):
        return compute()

    version = _version(path)
    full_key = (path, *key)

    hit, value = _lookup(path, version, key)
    if hit:
        return value

    # Single-flight. The dashboard fires ~25 requests at once, so on a cold
    # cache every one of them misses simultaneously and — without this — each
    # computes the identical answer in parallel, which is how the cache
    # bought nothing on the load that needed it most. Holding the lock across
    # ``compute()`` makes the rest wait for the first result instead.
    #
    # Deadlock safety: the lock is per key and nesting is strictly
    # hierarchical (recurring detection calls the transactions table, never
    # the reverse). Keep it that way — a cycle between two cached keys would
    # deadlock here.
    with _single_flight_lock(full_key):
        # A waiter arrives after the holder has published; re-check first.
        hit, value = _lookup(path, version, key)
        if hit:
            return value

        value = compute()

        # Re-read the version: ``compute()`` may have taken long enough for a
        # write to land, which would make the value just built already stale.
        if _version(path) != version or _has_pending_state(db):
            return value

        with _lock:
            generation = _generations.get(path)
            if generation is None or generation[0] != version:
                # First entry of a new generation — the previous one is stale
                # in its entirety, so it is replaced rather than added to.
                generation = (version, {})
                _generations[path] = generation
            generation[1][key] = value
        return value


def clear() -> None:
    """Drop every cached entry.

    Used when a database file is replaced underneath the process (backup
    restore, demo rebuild) and in test teardown.
    """
    with _lock:
        _generations.clear()


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _bump(_session: Session) -> None:
    """Invalidate every generation after a commit or rollback."""
    global _write_counter
    with _lock:
        _write_counter += 1
