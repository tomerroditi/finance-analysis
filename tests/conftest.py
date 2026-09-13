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

import pytest

from typing import Generator

import keyring
import keyring.backend
import keyring.errors
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
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
        "FAD_CATEGORIES_ICONS_PATH",
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


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
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
