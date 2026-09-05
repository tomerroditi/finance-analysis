"""Tests for the database backup/restore utility.

Covers the ``restore_backup`` path-resolution fix for py/path-injection
(CodeQL alerts #2/#3): the filename is matched against the backup
directory's real listing rather than joined onto it directly, so a
filename that passes the ``data_YYYYMMDD_HHMMSS.db`` shape check but has
no matching file must still raise ``FileNotFoundError``, and a filename
that does match an existing backup must still restore successfully.

Uses ``tmp_path`` + ``AppConfig._base_user_dir`` overrides exclusively —
never the real ``~/.finance-analysis/`` directory.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import AppConfig
from backend.utils.backup import get_backup_dir, restore_backup


@pytest.fixture(autouse=True)
def reset_config():
    """Reset AppConfig singleton state between tests."""
    config = AppConfig()
    original_base_dir = config._base_user_dir
    original_forced_mode = AppConfig._forced_mode
    yield
    config._base_user_dir = original_base_dir
    AppConfig._forced_mode = original_forced_mode


def _make_sqlite_file(path: Path) -> None:
    """Create a minimal, valid SQLite database file at ``path``."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO marker (note) VALUES ('from backup')")
        conn.commit()
    finally:
        conn.close()


class TestRestoreBackupMissingFile:
    """A filename shaped like a backup but absent from the directory."""

    def test_raises_file_not_found_when_no_matching_entry(self, tmp_path):
        """Regex-valid filename with no directory entry raises FileNotFoundError.

        This is the behaviour the directory-listing lookup must preserve:
        CodeQL now sees the resolved path come from a trusted enumeration
        of ``backup_dir`` instead of a direct join of the raw filename, but
        the outward behaviour — same exception, same message shape — is
        unchanged.
        """
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        get_backup_dir().mkdir(parents=True, exist_ok=True)

        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            restore_backup("data_20260101_000000.db")

    def test_raises_file_not_found_when_backup_dir_absent(self, tmp_path):
        """No backup directory at all also raises FileNotFoundError, not OSError."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        assert not get_backup_dir().exists()

        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            restore_backup("data_20260101_000000.db")


class TestRestoreBackupSuccess:
    """A filename that matches an existing backup file."""

    def test_restores_existing_backup(self, tmp_path):
        """A valid, existing backup file is copied over the active database.

        Heavy side effects unrelated to the path-resolution fix (engine
        disposal, the post-restore Alembic upgrade) are mocked so the test
        stays focused and fast; the actual SQLite copy runs for real.
        """
        config = AppConfig()
        config._base_user_dir = str(tmp_path)

        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "data_20260101_000000.db"
        _make_sqlite_file(backup_file)

        with (
            patch("backend.database.reset_engines"),
            patch("backend.utils.backup._upgrade_restored_db"),
        ):
            restore_backup("data_20260101_000000.db")

        db_path = Path(config.get_db_path())
        assert db_path.is_file()

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT note FROM marker").fetchall()
        finally:
            conn.close()
        assert rows == [("from backup",)]
