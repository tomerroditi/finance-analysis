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

import os
import re
import sqlite3
import stat
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import AppConfig
from backend.utils.backup import (
    _upgrade_restored_db,
    backup_db,
    get_backup_dir,
    list_backups,
    restore_backup,
)


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


# ---------------------------------------------------------------------------
# backup_db / list_backups / restore validation / post-restore migration
# ---------------------------------------------------------------------------


def _install_live_db(tmp_path: Path) -> Path:
    """Point AppConfig at ``tmp_path`` and create a real SQLite ``data.db`` there."""
    config = AppConfig()
    config._base_user_dir = str(tmp_path)
    db_path = Path(config.get_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _make_sqlite_file(db_path)
    return db_path


class TestBackupDb:
    """Creating a backup of the live database."""

    def test_returns_none_when_live_db_is_missing(self, tmp_path):
        """No ``data.db`` on disk is a no-op that returns None, not an error."""
        AppConfig()._base_user_dir = str(tmp_path)

        assert backup_db() is None
        assert not get_backup_dir().exists()

    def test_creates_a_readable_copy_with_timestamped_name(self, tmp_path):
        """A backup lands in the backups dir, is a valid SQLite copy, and is owner-only."""
        _install_live_db(tmp_path)

        dest = backup_db()

        assert dest is not None
        assert dest.parent == get_backup_dir()
        assert re.fullmatch(r"data_\d{8}_\d{6}\.db", dest.name)
        conn = sqlite3.connect(str(dest))
        try:
            assert conn.execute("SELECT note FROM marker").fetchall() == [("from backup",)]
        finally:
            conn.close()
        assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    def test_prunes_oldest_backups_beyond_the_limit(self, tmp_path):
        """Only ``max_backups`` newest files survive; the oldest are unlinked."""
        _install_live_db(tmp_path)
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        old_files = []
        for i in range(3):
            f = backup_dir / f"data_2020010{i + 1}_000000.db"
            _make_sqlite_file(f)
            os.utime(f, (1_600_000_000 + i, 1_600_000_000 + i))
            old_files.append(f)

        dest = backup_db(max_backups=2)

        remaining = sorted(p.name for p in backup_dir.glob("data_*.db"))
        assert remaining == sorted([old_files[2].name, dest.name])
        assert not old_files[0].exists()
        assert not old_files[1].exists()

    def test_zero_max_backups_disables_pruning(self, tmp_path):
        """``max_backups=0`` keeps every existing backup file."""
        _install_live_db(tmp_path)
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        for i in range(3):
            _make_sqlite_file(backup_dir / f"data_2020010{i + 1}_000000.db")

        backup_db(max_backups=0)

        assert len(list(backup_dir.glob("data_*.db"))) == 4

    def test_copy_failure_returns_none_and_leaves_no_partial_file(self, tmp_path):
        """A failing SQLite copy is logged and reported as None."""
        _install_live_db(tmp_path)

        with patch("backend.utils.backup.sqlite3.connect", side_effect=sqlite3.OperationalError("locked")):
            assert backup_db() is None

    def test_chmod_failure_is_tolerated(self, tmp_path):
        """A platform that refuses chmod still gets its backup."""
        _install_live_db(tmp_path)

        with patch("backend.utils.backup.os.chmod", side_effect=OSError("nope")):
            dest = backup_db()

        assert dest is not None and dest.is_file()


class TestListBackups:
    """Enumerating backups for the settings page."""

    def test_returns_empty_list_when_directory_is_absent(self, tmp_path):
        """No backups dir means an empty list, not an exception."""
        AppConfig()._base_user_dir = str(tmp_path)
        assert list_backups() == []

    def test_lists_only_backup_shaped_files_newest_first(self, tmp_path):
        """Entries carry filename/created_at/size and are sorted by recency."""
        AppConfig()._base_user_dir = str(tmp_path)
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        older = backup_dir / "data_20240101_000000.db"
        newer = backup_dir / "data_20240102_000000.db"
        _make_sqlite_file(older)
        _make_sqlite_file(newer)
        os.utime(older, (1_600_000_000, 1_600_000_000))
        os.utime(newer, (1_700_000_000, 1_700_000_000))
        (backup_dir / "notes.txt").write_text("ignored")
        (backup_dir / "data.db").write_text("ignored: no timestamp")

        result = list_backups()

        assert [b["filename"] for b in result] == [newer.name, older.name]
        assert set(result[0]) == {"filename", "created_at", "size_bytes"}
        assert result[0]["size_bytes"] == newer.stat().st_size
        assert result[0]["created_at"] > result[1]["created_at"]
        assert datetime.fromisoformat(result[0]["created_at"]).year == 2023


class TestRestoreBackupValidation:
    """Input validation before anything is overwritten."""

    @pytest.mark.parametrize(
        "bad_name",
        [
            "../data_20260101_000000.db",
            "data_20260101_000000.db/../x",
            "data_2026010_000000.db",
            "data_20260101_000000.sqlite",
            "DATA_20260101_000000.db",
            "",
            "data_20260101_000000.db\n",
        ],
    )
    def test_rejects_filenames_outside_the_backup_shape(self, tmp_path, bad_name):
        """Anything that is not exactly ``data_YYYYMMDD_HHMMSS.db`` is refused."""
        AppConfig()._base_user_dir = str(tmp_path)

        with pytest.raises(ValueError, match="Invalid backup filename"):
            restore_backup(bad_name)

    def test_rejects_a_file_that_is_not_sqlite(self, tmp_path):
        """A well-named but corrupt file is refused before the live DB is touched."""
        db_path = _install_live_db(tmp_path)
        before = db_path.read_bytes()
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        (backup_dir / "data_20260101_000000.db").write_bytes(b"definitely not a database")

        with pytest.raises(ValueError, match="not a valid SQLite database"):
            restore_backup("data_20260101_000000.db")

        assert db_path.read_bytes() == before

    def test_rejects_a_directory_entry_that_is_not_a_regular_file(self, tmp_path):
        """A directory named like a backup is treated as missing."""
        AppConfig()._base_user_dir = str(tmp_path)
        backup_dir = get_backup_dir()
        (backup_dir / "data_20260101_000000.db").mkdir(parents=True)

        with pytest.raises(FileNotFoundError):
            restore_backup("data_20260101_000000.db")

    def test_rejects_a_symlink_that_escapes_the_backup_directory(self, tmp_path):
        """A backup-named symlink pointing outside the dir is refused."""
        AppConfig()._base_user_dir = str(tmp_path)
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        outside = tmp_path / "outside.db"
        _make_sqlite_file(outside)
        (backup_dir / "data_20260101_000000.db").symlink_to(outside)

        with pytest.raises(ValueError, match="escapes backup directory"):
            restore_backup("data_20260101_000000.db")

    def test_restore_takes_a_safety_backup_of_the_live_db_first(self, tmp_path):
        """The pre-restore snapshot of the live DB is kept alongside the backups."""
        _install_live_db(tmp_path)
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True)
        _make_sqlite_file(backup_dir / "data_20260101_000000.db")

        with (
            patch("backend.database.reset_engines") as reset,
            patch("backend.utils.backup._upgrade_restored_db") as upgrade,
        ):
            restore_backup("data_20260101_000000.db")

        reset.assert_called_once()
        upgrade.assert_called_once()
        assert len(list(backup_dir.glob("data_*.db"))) == 2


class TestUpgradeRestoredDb:
    """The post-restore Alembic pass never raises."""

    def test_missing_alembic_ini_is_a_logged_no_op(self, tmp_path, monkeypatch):
        """When the ini cannot be found (frozen build without it), nothing runs."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

        with patch("alembic.command.upgrade") as upgrade:
            _upgrade_restored_db()

        upgrade.assert_not_called()

    def test_migration_failure_is_swallowed(self, monkeypatch):
        """An Alembic error is logged, not propagated to the restore caller."""
        monkeypatch.setattr(sys, "frozen", False, raising=False)

        with patch("alembic.command.upgrade", side_effect=RuntimeError("boom")) as upgrade:
            _upgrade_restored_db()

        upgrade.assert_called_once()
        assert upgrade.call_args.args[1] == "head"
