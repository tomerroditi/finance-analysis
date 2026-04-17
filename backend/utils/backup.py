"""
Database backup utility.

Creates and restores backups of the SQLite database using Python's sqlite3.backup()
API, which is safe to run while the database is in use.
"""

import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.config import AppConfig

logger = logging.getLogger(__name__)

MAX_BACKUPS = 5

# Backup filenames always follow ``data_YYYYMMDD_HHMMSS.db``. Restrict restore
# input to this shape so a malicious filename cannot traverse out of the
# backup directory (e.g. ``../../etc/passwd``) or point at arbitrary files.
_BACKUP_FILENAME_RE = re.compile(r"^data_\d{8}_\d{6}\.db$")


def get_backup_dir() -> Path:
    """Get the backup directory path."""
    return Path(AppConfig().get_user_dir()) / "backups"


def backup_db(max_backups: int = MAX_BACKUPS) -> Path | None:
    """Create a backup of the SQLite database.

    Uses SQLite's online backup API which is safe during concurrent access.

    Parameters
    ----------
    max_backups : int
        Maximum number of backups to keep. When exceeded, the oldest is deleted.
        Set to 0 to disable pruning.

    Returns
    -------
    Path or None
        Path to the created backup file, or None if backup failed.
    """
    config = AppConfig()
    src = Path(config.get_db_path())
    if not src.exists():
        logger.warning("Database file not found at %s, skipping backup", src)
        return None

    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"data_{timestamp}.db"

    try:
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dest))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        try:
            os.chmod(dest, 0o600)
        except OSError:
            logger.debug("Unable to chmod backup %s", dest)
        logger.info("Database backed up to %s", dest)
    except Exception:
        logger.exception("Database backup failed")
        return None

    # Prune oldest backups beyond the limit
    if max_backups > 0:
        backups = sorted(backup_dir.glob("data_*.db"), key=lambda f: f.stat().st_mtime)
        while len(backups) > max_backups:
            old = backups.pop(0)
            old.unlink()
            logger.info("Pruned old backup %s", old.name)

    return dest


def list_backups() -> list[dict]:
    """List available backup files.

    Returns
    -------
    list of dict
        Each dict has ``filename``, ``created_at`` (ISO string), and ``size_bytes``.
        Sorted by creation time, newest first.
    """
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []

    backups = []
    for f in backup_dir.glob("data_*.db"):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_bytes": stat.st_size,
        })

    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


def restore_backup(filename: str) -> None:
    """Restore the database from a backup file.

    Backs up the current database before restoring, then replaces
    the active database with the selected backup. The DB engine is
    disposed before overwriting so no stale connections interfere.

    Parameters
    ----------
    filename : str
        Name of the backup file to restore (e.g. ``data_20260330_120000.db``).

    Raises
    ------
    FileNotFoundError
        If the backup file does not exist.
    ValueError
        If the filename is not a valid backup name, escapes the backup
        directory, or the file is not a readable SQLite database.
    """
    # Reject anything that isn't a plain backup filename — no slashes, no
    # traversal, no symlinks pointing elsewhere.
    if not _BACKUP_FILENAME_RE.match(filename):
        raise ValueError(f"Invalid backup filename: {filename}")

    backup_dir = get_backup_dir().resolve()
    backup_path = (backup_dir / filename).resolve()
    try:
        backup_path.relative_to(backup_dir)
    except ValueError as exc:
        raise ValueError(f"Backup path escapes backup directory: {filename}") from exc

    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    # Validate the file is actually a readable SQLite database before we
    # overwrite the live DB — prevents restoring a corrupt or hostile file.
    try:
        test_conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        try:
            test_conn.execute("PRAGMA schema_version").fetchone()
        finally:
            test_conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Backup file is not a valid SQLite database: {filename}") from exc

    config = AppConfig()
    db_path = Path(config.get_db_path())

    # Safety: backup current DB before restoring (no pruning, to avoid
    # deleting the backup we're about to restore)
    backup_db(max_backups=0)

    # Dispose the SQLAlchemy engine so no connections hold the DB file open
    from backend.database import reset_engine

    reset_engine()

    # Restore: copy backup over the active database
    src_conn = sqlite3.connect(str(backup_path))
    dst_conn = sqlite3.connect(str(db_path))
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    try:
        os.chmod(db_path, 0o600)
    except OSError:
        logger.debug("Unable to chmod restored DB %s", db_path)

    logger.info("Database restored from %s", filename)
