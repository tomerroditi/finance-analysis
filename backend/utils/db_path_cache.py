"""Partition key for process-wide in-memory caches.

Real mode, demo mode and every per-visitor demo sandbox (see
``backend/demo_sessions.py``) each resolve to a different database file, so a
module-level cache keyed by that path can never serve one context's data to
another. ``CredentialsService`` and ``CategoriesTagsService`` key their caches
this way; ``demo_sessions`` drops a sandbox's entries by the same path when
its file is replaced.
"""

from backend.config import AppConfig


def cache_key() -> str:
    """Return the cache partition for the current context (its DB path).

    Returns
    -------
    str
        The resolved database path of the current request's mode.
    """
    return AppConfig().get_db_path()
