"""Root fixtures: in-memory SQLite plus process-wide isolation guards.

Every test in the tree runs under two autouse guards defined here:

* ``_isolated_app_config`` points ``FAD_USER_DIR`` at a per-test ``tmp_path``
  and resets the ``AppConfig`` singleton (base-dir override, forced-mode pin,
  demo contextvar) and the SQLAlchemy engine registry before and after each
  test. Without it a single test that pins the singleton to the resolved
  ``~/.finance-analysis`` path leaks that pin into every later test, and the
  suite writes ``data.db``, ``demo_env/demo_data.db`` and real backups into
  the developer's home directory.
* ``_in_memory_keyring`` swaps the OS keyring for an in-memory backend for
  the whole session (and empties it before every test), so credential writes
  never reach a developer's Keychain or a plaintext keyring file.
"""

import sqlite3
import threading
from collections.abc import Generator
from typing import Any

import keyring
import keyring.backend
import keyring.errors
import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.models.base import Base


class _MemoryKeyring(keyring.backend.KeyringBackend):
    """Dict-backed keyring with the same not-found semantics as a real one."""

    priority = 1

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):
        """Return the stored secret or ``None`` when no entry exists."""
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store ``password`` under ``(service, username)``."""
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        """Delete an entry, raising ``PasswordDeleteError`` when absent."""
        try:
            del self.store[(service, username)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError(
                f"no entry for {service}/{username}"
            )


@pytest.fixture(scope="session", autouse=True)
def _in_memory_keyring() -> Generator[_MemoryKeyring, None, None]:
    """Route every ``keyring`` call in the session to an in-memory backend."""
    previous = keyring.get_keyring()
    backend = _MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def memory_keyring(_in_memory_keyring: _MemoryKeyring) -> _MemoryKeyring:
    """Hand each test an empty in-memory keyring to inspect or seed."""
    _in_memory_keyring.store.clear()
    return _in_memory_keyring


@pytest.fixture(autouse=True)
def _isolated_app_config(tmp_path, monkeypatch) -> Generator[str, None, None]:
    """Sandbox ``AppConfig`` and the engine registry for one test.

    Yields the per-test user directory (as a string) that ``FAD_USER_DIR``
    points at. Tests that need a different layout may still assign
    ``AppConfig()._base_user_dir`` or ``monkeypatch.setenv("FAD_USER_DIR")``
    themselves — both are undone here.
    """
    from backend import database
    from backend.config import AppConfig, _demo_mode_ctx

    user_dir = str(tmp_path / "fad-user")
    monkeypatch.setenv("FAD_USER_DIR", user_dir)
    for var in (
        "FAD_DB_PATH",
        "FAD_CREDENTIALS_PATH",
        "FAD_CATEGORIES_PATH",
    ):
        monkeypatch.delenv(var, raising=False)

    config = AppConfig()
    config._base_user_dir_override = None
    AppConfig._forced_mode = None
    token = _demo_mode_ctx.set(False)
    database.reset_engines()
    try:
        yield user_dir
    finally:
        database.reset_engines()
        config._base_user_dir_override = None
        AppConfig._forced_mode = None
        _demo_mode_ctx.reset(token)


_schema_template: sqlite3.Connection | None = None
_schema_template_lock = threading.Lock()


def _copy_schema(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
    """Clone the pre-built schema into a freshly opened in-memory connection.

    ``Base.metadata.create_all`` costs ~13 ms per database (a PRAGMA probe and
    a CREATE per table); SQLite's backup API copies the finished schema in
    well under 1 ms. The template is built once per process, on first use.
    """
    global _schema_template
    with _schema_template_lock:
        if _schema_template is None:
            builder = create_engine("sqlite://")
            Base.metadata.create_all(builder)
            template = sqlite3.connect(":memory:", check_same_thread=False)
            with builder.connect() as connection:
                connection.connection.driver_connection.backup(template)
            builder.dispose()
            _schema_template = template
        _schema_template.backup(dbapi_connection)


def make_memory_engine(**kwargs: Any) -> Engine:
    """Create an in-memory SQLite engine that starts with every table.

    Keyword arguments are forwarded to ``create_engine`` (e.g. ``poolclass``).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        **kwargs,
    )
    event.listen(engine, "connect", _copy_schema)
    return engine


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = make_memory_engine()
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a session for database operations."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
