"""
Backup management API routes.

Provides endpoints for creating, listing, and restoring database backups.
When Google Drive is connected, operations target Drive. Otherwise, local backups.
"""

import os
import shutil
import tempfile
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.google_drive_service import GoogleDriveService
from backend.utils.backup import backup_db, list_backups, restore_backup
from backend.utils.cloud_backup import create_backup_bundle, restore_backup_bundle

router = APIRouter()


class BackupInfo(BaseModel):
    """Single backup file info."""

    filename: str
    created_at: str
    size_bytes: int


class RestoreRequest(BaseModel):
    """Request body for restoring a backup."""

    filename: str


def _is_google_connected() -> bool:
    """Check if Google Drive is connected."""
    try:
        return GoogleDriveService().is_connected()
    except Exception:
        return False


@router.get("/", response_model=list[BackupInfo])
def get_backups():
    """List all available database backups (Drive or local)."""
    if _is_google_connected():
        service = GoogleDriveService()
        drive_backups = service.list_backups()
        return [
            BackupInfo(
                filename=b["name"],
                created_at=b.get("createdTime", ""),
                size_bytes=0,
            )
            for b in drive_backups
        ]
    return list_backups()


@router.post("/", response_model=BackupInfo)
def create_backup():
    """Create a new database backup (Drive or local)."""
    if _is_google_connected():
        service = GoogleDriveService()
        drive_service = service._get_drive_service()
        folder_id = service._get_or_create_backup_folder(drive_service)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        bundle = create_backup_bundle()
        service.upload_backup(folder_id, timestamp, bundle)

        bundle_dir = os.path.dirname(next(iter(bundle.values())))
        shutil.rmtree(bundle_dir, ignore_errors=True)

        return BackupInfo(
            filename=timestamp,
            created_at=datetime.now().isoformat(),
            size_bytes=0,
        )

    path = backup_db()
    if path is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Backup failed")

    stat = path.stat()
    return BackupInfo(
        filename=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        size_bytes=stat.st_size,
    )


@router.post("/restore")
def restore_from_backup(request: RestoreRequest):
    """Restore database from a backup (Drive or local)."""
    if _is_google_connected():
        service = GoogleDriveService()
        drive_backups = service.list_backups()

        target = None
        for b in drive_backups:
            if b["name"] == request.filename:
                target = b
                break

        if not target:
            from backend.errors import EntityNotFoundException

            raise EntityNotFoundException(f"Cloud backup not found: {request.filename}")

        tmp_dir = tempfile.mkdtemp(prefix="fad_restore_")
        try:
            service.download_backup(target["id"], tmp_dir)
            restore_backup_bundle(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return {"status": "restored", "filename": request.filename}

    try:
        restore_backup(request.filename)
    except FileNotFoundError as e:
        from backend.errors import EntityNotFoundException

        raise EntityNotFoundException(str(e))

    return {"status": "restored", "filename": request.filename}
