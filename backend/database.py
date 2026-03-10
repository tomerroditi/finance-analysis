"""
Database connection and session management for the FastAPI backend.

This module provides pure SQLAlchemy database connection handling,
replacing the Streamlit-specific database connection used in the original app.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import AppConfig


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

    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Create the database file if it doesn't exist
    if not os.path.exists(db_path):
        with open(db_path, "w"):
            pass

    return create_engine(
        get_database_url(db_path),
        echo=echo,
        connect_args={"check_same_thread": False},  # Required for SQLite with FastAPI
        poolclass=NullPool,  # Create fresh connections for thread safety
    )


# Default engine and session factory
_engine = None
_SessionLocal = None


def get_engine(db_path: str = None):
    """
    Get or create the default database engine.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    Engine
        SQLAlchemy engine instance.
    """
    global _engine
    if _engine is None:
        _engine = create_db_engine(db_path)
    return _engine


def get_session_factory(db_path: str = None):
    """
    Get or create the session factory.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    sessionmaker
        SQLAlchemy session factory.
    """
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(db_path)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


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


def reset_engine():
    """
    Reset the global engine and session factory.

    Useful for testing or when switching databases.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
