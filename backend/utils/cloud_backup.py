"""
Cloud backup utility for Google Drive.

Orchestrates backup bundle creation (DB snapshot + config files),
upload to Google Drive, and tiered retention pruning.
"""

import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from backend.config import AppConfig

logger = logging.getLogger(__name__)

RECENT_KEEP = 5
WEEKLY_MAX_AGE_WEEKS = 12


def compute_backups_to_prune(backups: list[dict]) -> list[dict]:
    """Determine which backups should be deleted based on tiered retention.

    Retention policy:
    - Keep the 5 most recent backups unconditionally.
    - For older backups: keep only the newest per ISO week.
    - Delete weekly backups older than 12 weeks.

    Parameters
    ----------
    backups : list of dict
        Each dict must have 'id' and 'name' (timestamp format: YYYYMMDD_HHMMSS).

    Returns
    -------
    list of dict
        Backups that should be deleted.
    """
    if len(backups) <= RECENT_KEEP:
        return []

    sorted_backups = sorted(backups, key=lambda b: b["name"], reverse=True)

    to_prune = []
    now = datetime.now()
    cutoff = now - timedelta(weeks=WEEKLY_MAX_AGE_WEEKS)

    weekly_best: dict[tuple[int, int], dict] = {}
    for b in sorted_backups[RECENT_KEEP:]:
        try:
            ts = datetime.strptime(b["name"], "%Y%m%d_%H%M%S")
        except ValueError:
            continue

        if ts < cutoff:
            to_prune.append(b)
            continue

        iso_year, iso_week, _ = ts.isocalendar()
        week_key = (iso_year, iso_week)

        if week_key not in weekly_best:
            weekly_best[week_key] = b
        else:
            to_prune.append(b)

    return to_prune


def create_backup_bundle(dest_dir: str | None = None) -> dict[str, str]:
    """Create a local backup bundle (DB snapshot + config files).

    Parameters
    ----------
    dest_dir : str, optional
        Directory to write bundle files. Uses a temp dir if not specified.

    Returns
    -------
    dict
        Mapping of filename -> local path for each file in the bundle.
    """
    config = AppConfig()
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="fad_backup_")

    os.makedirs(dest_dir, exist_ok=True)
    files = {}

    db_path = config.get_db_path()
    if os.path.exists(db_path):
        raw_backup = os.path.join(dest_dir, "data.db")
        src_conn = sqlite3.connect(db_path)
        dst_conn = sqlite3.connect(raw_backup)
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        gz_path = os.path.join(dest_dir, "data.db.gz")
        with open(raw_backup, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(raw_backup)
        files["data.db.gz"] = gz_path

    for filename, getter in [
        ("categories.yaml", config.get_categories_path),
        ("categories_icons.yaml", config.get_categories_icons_path),
    ]:
        src = getter()
        if os.path.exists(src):
            dest = os.path.join(dest_dir, filename)
            shutil.copy2(src, dest)
            files[filename] = dest

    return files


def restore_backup_bundle(bundle_dir: str) -> None:
    """Restore a downloaded backup bundle to the user directory.

    Decompresses the DB file and copies config files to the user dir.
    Resets the DB engine so subsequent queries use the restored data.

    Parameters
    ----------
    bundle_dir : str
        Directory containing the downloaded bundle files.
    """
    from backend.database import reset_engine
    from backend.utils.backup import backup_db

    config = AppConfig()

    backup_db(max_backups=0)
    reset_engine()

    gz_path = os.path.join(bundle_dir, "data.db.gz")
    if os.path.exists(gz_path):
        db_path = config.get_db_path()
        with gzip.open(gz_path, "rb") as f_in, open(db_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        logger.info("Restored database from cloud backup")

    user_dir = config.get_user_dir()
    for filename in ("categories.yaml", "categories_icons.yaml"):
        src = os.path.join(bundle_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(user_dir, filename))
            logger.info("Restored %s from cloud backup", filename)


class BackupScheduler:
    """Debounce-based backup scheduler.

    Parameters
    ----------
    drive_service : GoogleDriveService
        Service for checking connection and uploading backups.
    debounce_seconds : int
        Seconds to wait after last DB commit before triggering backup.
    """

    def __init__(self, drive_service, debounce_seconds: int = 300):
        self._drive_service = drive_service
        self._debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def is_pending(self) -> bool:
        """Return True if a backup timer is currently running."""
        with self._lock:
            return self._timer is not None and self._timer.is_alive()

    def schedule(self) -> None:
        """Schedule a backup, resetting any pending timer.

        Does nothing if in demo mode or Google is not connected.
        """
        if AppConfig().is_demo_mode:
            return
        if not self._drive_service.is_connected():
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._run_backup)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        """Cancel any pending backup timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def flush(self) -> None:
        """If a backup is pending, run it immediately (for shutdown)."""
        if self.is_pending:
            self.cancel()
            self._run_backup()

    def _run_backup(self) -> None:
        """Execute the backup: create bundle, upload to Drive, prune old backups."""
        try:
            drive_service = self._drive_service._get_drive_service()
            if not drive_service:
                logger.warning("Cannot run cloud backup: Drive service unavailable")
                return

            folder_id = self._drive_service._get_or_create_backup_folder(drive_service)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            bundle = create_backup_bundle()
            if not bundle:
                logger.warning("No files to back up")
                return

            self._drive_service.upload_backup(folder_id, timestamp, bundle)
            logger.info("Cloud backup uploaded: %s", timestamp)

            bundle_dir = os.path.dirname(next(iter(bundle.values())))
            shutil.rmtree(bundle_dir, ignore_errors=True)

            all_backups = self._drive_service.list_backups(drive_service, folder_id)
            to_prune = compute_backups_to_prune(all_backups)
            for b in to_prune:
                self._drive_service.delete_backup(b["id"])
                logger.info("Pruned old cloud backup: %s", b["name"])

        except Exception:
            logger.exception("Cloud backup failed")
