"""Tests for engine creation and URL resolution in ``backend.database``.

The registry (engine/session-factory caching) is covered in
``test_database_registry.py``; this file covers the file-system side of
``create_db_engine`` — directory and file creation with owner-only
permissions — and the ``AppConfig`` fallback when no path is given.
"""

import stat
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from backend.config import AppConfig
from backend.database import create_db_engine, get_database_url


class TestGetDatabaseUrl:
    """Building the SQLAlchemy URL."""

    def test_explicit_path_is_used_verbatim(self):
        """An explicit path becomes a three-slash sqlite URL."""
        assert get_database_url("/tmp/x/data.db") == "sqlite:////tmp/x/data.db"

    def test_default_path_comes_from_app_config(self):
        """With no argument the URL points at the config's current DB path."""
        with patch.object(AppConfig, "get_db_path", return_value="/cfg/data.db"):
            assert get_database_url() == "sqlite:////cfg/data.db"


class TestCreateDbEngine:
    """Creating the on-disk engine."""

    def test_creates_missing_directory_and_file_with_private_permissions(self, tmp_path):
        """A nested, non-existent path is created as 0o700 dir + 0o600 file."""
        db_path = tmp_path / "nested" / "deeper" / "data.db"

        engine = create_db_engine(str(db_path))
        try:
            assert db_path.is_file()
            assert stat.S_IMODE(db_path.parent.stat().st_mode) == 0o700
            assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
            assert isinstance(engine.pool, NullPool)
            with engine.connect() as conn:
                assert conn.execute(text("select 1")).scalar() == 1
        finally:
            engine.dispose()

    def test_existing_file_is_not_truncated(self, tmp_path):
        """An existing database file keeps its content."""
        db_path = tmp_path / "data.db"
        engine = create_db_engine(str(db_path))
        with engine.connect() as conn:
            conn.execute(text("create table t (x integer)"))
            conn.execute(text("insert into t values (42)"))
            conn.commit()
        engine.dispose()

        engine = create_db_engine(str(db_path))
        try:
            with engine.connect() as conn:
                assert conn.execute(text("select x from t")).scalar() == 42
        finally:
            engine.dispose()

    def test_chmod_failures_are_ignored(self, tmp_path):
        """Filesystems that refuse chmod (e.g. some mounts) still get an engine."""
        db_path = tmp_path / "data.db"

        with patch("backend.database.os.chmod", side_effect=OSError("read-only attrs")):
            engine = create_db_engine(str(db_path))
        try:
            assert db_path.is_file()
        finally:
            engine.dispose()

    def test_default_path_resolves_through_app_config(self, tmp_path):
        """With no argument the engine is built at the config's DB path."""
        db_path = tmp_path / "cfg" / "data.db"

        with patch.object(AppConfig, "get_db_path", return_value=str(db_path)):
            engine = create_db_engine()
        try:
            assert db_path.is_file()
            assert str(engine.url) == f"sqlite:///{db_path}"
        finally:
            engine.dispose()
