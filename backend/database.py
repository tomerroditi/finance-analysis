"""
Database connection and session management for the FastAPI backend.

This module provides pure SQLAlchemy database connection handling,
replacing the Streamlit-specific database connection used in the original app.
"""

import os
import threading
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import AppConfig

# Importing for side effect: registers the Session event listeners that
# clear the per-session DataFrame cache on commit/rollback. Everything that
# opens a session imports this module, so registration is guaranteed.
import backend.utils.session_cache  # noqa: F401  (side-effect import)


def get_database_url(db_path: str = None) -> str:
    """
    Get the SQLAlchemy database URL for SQLite.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. If None, uses path from AppConfig.

    Returns
    -------
    str
        SQLAlchemy database URL.
    """
    if db_path is None:
        db_path = AppConfig().get_db_path()
    return f"sqlite:///{db_path}"


def create_db_engine(db_path: str = None, echo: bool = False):
    """
    Create a SQLAlchemy engine for the database.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    echo : bool
        If True, log all SQL statements.

    Returns
    -------
    Engine
        SQLAlchemy engine instance.
    """
    if db_path is None:
        db_path = AppConfig().get_db_path()

    # Ensure the directory exists with owner-only permissions. The DB
    # holds financial data; other users on a shared host should not be
    # able to list backups or read the DB file.
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)
    try:
        os.chmod(db_dir, 0o700)
    except OSError:
        pass

    # Create the database file if it doesn't exist
    if not os.path.exists(db_path):
        with open(db_path, "w"):
            pass
        try:
            os.chmod(db_path, 0o600)
        except OSError:
            pass

    return create_engine(
        get_database_url(db_path),
        echo=echo,
        connect_args={"check_same_thread": False},  # Required for SQLite with FastAPI
        poolclass=NullPool,  # Create fresh connections for thread safety
    )


# Engines and session factories, keyed by resolved database path. Keying on
# path rather than on the demo flag is more honest: it also covers the
# FAD_DB_PATH override without a special case, and two contexts that happen
# to resolve to the same file correctly share one engine.
_engines: dict[str, "Engine"] = {}
_session_factories: dict[str, sessionmaker] = {}

# Guards lazy creation. Requests are served from a threadpool, so two threads
# can miss the cache for the same path at once; without the lock they would
# each build an engine and one would be silently discarded.
_registry_lock = threading.Lock()


def get_engine(db_path: str = None):
    """
    Get or create the engine for a database path.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. When ``None``, resolves from
        ``AppConfig`` — which is demo-mode aware and therefore context-local.

    Returns
    -------
    Engine
        SQLAlchemy engine instance for that path.
    """
    if db_path is None:
        db_path = AppConfig().get_db_path()
    with _registry_lock:
        if db_path not in _engines:
            _engines[db_path] = create_db_engine(db_path)
        return _engines[db_path]


def get_session_factory(db_path: str = None):
    """
    Get or create the session factory for a database path.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. When ``None``, resolves from
        ``AppConfig``.

    Returns
    -------
    sessionmaker
        Session factory bound to that path's engine.
    """
    if db_path is None:
        db_path = AppConfig().get_db_path()
    engine = get_engine(db_path)
    with _registry_lock:
        if db_path not in _session_factories:
            _session_factories[db_path] = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
        return _session_factories[db_path]


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a database session and ensures it's closed after the request.
    Use this as a dependency in FastAPI route handlers.

    Yields
    ------
    Session
        SQLAlchemy session instance.

    Example
    -------
    ```python
    @app.get("/items")
    def get_items(db: Session = Depends(get_db)):
        return db.execute(select(Item)).scalars().all()
    ```
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions (for non-FastAPI usage).

    Use this when you need a database session outside of FastAPI routes,
    such as in background tasks or scripts.

    Yields
    ------
    Session
        SQLAlchemy session instance.

    Example
    -------
    ```python
    with get_db_context() as db:
        result = db.execute(select(Item)).scalars().all()
    ```
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_engine_for(db_path: str) -> None:
    """
    Dispose and drop the engine and factory for one database path.

    Parameters
    ----------
    db_path : str
        Path whose registry entries should be discarded.
    """
    with _registry_lock:
        engine = _engines.pop(db_path, None)
        _session_factories.pop(db_path, None)
    if engine is not None:
        engine.dispose()


def reset_engines() -> None:
    """
    Dispose and drop every cached engine and session factory.

    Used when a database file is replaced underneath the process (backup
    restore, demo-database rebuild) and in test teardown.
    """
    with _registry_lock:
        engines = list(_engines.values())
        _engines.clear()
        _session_factories.clear()
    for engine in engines:
        engine.dispose()
