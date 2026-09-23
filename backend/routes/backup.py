"""
Backup management API routes.

Provides endpoints for creating, listing, and restoring database backups.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.errors import BadRequestException, EntityNotFoundException
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
def get_backups() -> list[dict[str, Any]]:
    """List all available database backups."""
    return list_backups()


@router.post("/", response_model=BackupInfo)
def create_backup() -> BackupInfo:
    """Create a new database backup.

    Raises
    ------
    HTTPException
        500 when the backup could not be written.
    """
    path = backup_db()
    if path is None:
        raise HTTPException(status_code=500, detail="Backup failed")

    stat = path.stat()
    return BackupInfo(
        filename=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        size_bytes=stat.st_size,
    )


@router.post("/restore")
def restore_from_backup(request: RestoreRequest) -> dict[str, str]:
    """Restore database from a backup file.

    Creates a safety backup of the current database before restoring.
    Resets the DB engine so subsequent queries use the restored data.

    Raises
    ------
    EntityNotFoundException
        404 when the backup file does not exist.
    BadRequestException
        400 for an invalid filename or a file that is not a SQLite database.
    """
    try:
        restore_backup(request.filename)
    except FileNotFoundError as e:
        raise EntityNotFoundException(str(e)) from e
    except ValueError as e:
        # Invalid/traversal filenames and non-SQLite files are client input
        # problems — surface them as 400s, not sanitized 500s.
        raise BadRequestException(str(e)) from e

    return {"status": "restored", "filename": request.filename}
