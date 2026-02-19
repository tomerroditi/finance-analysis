"""Fixtures for route (API endpoint) tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.database import get_db
from backend.dependencies import get_database
from backend.models.base import Base


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite engine with StaticPool for route tests.

    StaticPool ensures all connections share the same in-memory database,
    which is required when the TestClient and test code use different
    connections to the same engine.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    """Create a session for database operations in route tests."""
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def test_client(db_session):
    """FastAPI TestClient with overridden database dependency."""

    def override_get_database():
        yield db_session

    app.dependency_overrides[get_database] = override_get_database
    app.dependency_overrides[get_db] = override_get_database
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
