"""
FastAPI dependencies for dependency injection.

This module provides common dependencies used across API routes.
"""

from typing import Generator

from sqlalchemy.orm import Session

from backend.database import get_db


def get_database() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    This is a wrapper around the database module's get_db function
    to be used as a FastAPI dependency.

    Yields
    ------
    Session
        SQLAlchemy session instance.
    """
    yield from get_db()
