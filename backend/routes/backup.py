"""
Backup management API routes.

Provides endpoints for creating, listing, and restoring database backups.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.utils.backup import backup_db, list_backups, restore_backup

router = APIRouter()


class BackupInfo(BaseModel):
    """Single backup file info."""

    filename: str
    created_at: str
    size_bytes: int


class RestoreRequest(BaseModel):
    """Request body for restoring a backup."""

    filename: str


@router.get("/", response_model=list[BackupInfo])
def get_backups():
    """List all available database backups."""
    return list_backups()


@router.post("/", response_model=BackupInfo)
def create_backup():
    """Create a new database backup."""
    path = backup_db()
    if path is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Backup failed")

    stat = path.stat()
    from datetime import datetime

    return BackupInfo(
        filename=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        size_bytes=stat.st_size,
    )


@router.post("/restore")
def restore_from_backup(request: RestoreRequest):
    """Restore database from a backup file.

    Creates a safety backup of the current database before restoring.
    Resets the DB engine so subsequent queries use the restored data.
    """
    try:
        restore_backup(request.filename)
    except FileNotFoundError as e:
        from backend.errors import EntityNotFoundException

        raise EntityNotFoundException(str(e))

    return {"status": "restored", "filename": request.filename}
