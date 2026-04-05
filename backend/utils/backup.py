"""
Database backup utility.

Creates and restores backups of the SQLite database using Python's sqlite3.backup()
API, which is safe to run while the database is in use.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.config import AppConfig

logger = logging.getLogger(__name__)

MAX_BACKUPS = 5


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
    """
    backup_dir = get_backup_dir()
    backup_path = backup_dir / filename

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {filename}")

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

    logger.info("Database restored from %s", filename)


def is_db_empty() -> bool:
    """Check if the database has no user transaction data.

    Used for new-machine detection — the DB exists (created by create_all)
    but has no actual user data.

    Returns
    -------
    bool
        True if all transaction tables are empty.
    """
    from sqlalchemy import text

    from backend.database import get_db_context

    tables = [
        "bank_transactions",
        "credit_card_transactions",
        "cash_transactions",
        "manual_investment_transactions",
    ]
    with get_db_context() as db:
        for table in tables:
            count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if count > 0:
                return False
    return True
