"""Session-scoped DataFrame cache for expensive full-table reads.

FastAPI creates one SQLAlchemy session per request (``get_db``), so a cache
stored in ``Session.info`` is exactly request-scoped: it dies with the
session and is never shared across requests. Analytics endpoints call the
same "load all transactions" paths repeatedly within one request (e.g.
``get_cash_flow_forecast`` triggers three independent full reloads); this
cache collapses those to one read.

Invalidation: every repository write method commits immediately, so the
cache is cleared on every ``commit()`` / ``rollback()`` via global Session
event listeners. A long-lived session (tests, the scrape pipeline) therefore
never observes stale frames after a write.
"""

from typing import Hashable

import pandas as pd
from sqlalchemy import event
from sqlalchemy.orm import Session

_INFO_KEY = "_dataframe_cache"


def session_cache_get(db: Session, key: tuple[Hashable, ...]) -> pd.DataFrame | None:
    """Return a copy of the cached frame for ``key``, or None on miss.

    Parameters
    ----------
    db : Session
        The request-scoped SQLAlchemy session.
    key : tuple
        Hashable cache key, namespaced by the caller
        (e.g. ``("transactions.get_table", service, ...)``).

    Returns
    -------
    pd.DataFrame | None
        A defensive copy of the cached frame (callers routinely mutate
        DataFrames in place), or None when absent.
    """
    cached = db.info.get(_INFO_KEY, {}).get(key)
    return cached.copy() if cached is not None else None


def session_cache_set(db: Session, key: tuple[Hashable, ...], df: pd.DataFrame) -> None:
    """Store a copy of ``df`` in the session cache under ``key``.

    Parameters
    ----------
    db : Session
        The request-scoped SQLAlchemy session.
    key : tuple
        Hashable cache key.
    df : pd.DataFrame
        Frame to cache. A copy is stored so later caller-side mutation
        of ``df`` cannot corrupt the cache.
    """
    db.info.setdefault(_INFO_KEY, {})[key] = df.copy()


def _clear_cache(session: Session) -> None:
    """Clear the DataFrame cache on the session."""
    session.info.pop(_INFO_KEY, None)


@event.listens_for(Session, "after_commit")
def _clear_on_commit(session: Session) -> None:
    """Drop the cache after any commit — table contents may have changed."""
    _clear_cache(session)


@event.listens_for(Session, "after_rollback")
def _clear_on_rollback(session: Session) -> None:
    """Drop the cache after any rollback — in-flight state is discarded."""
    _clear_cache(session)
