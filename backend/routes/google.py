"""
Google account management API routes.

Handles OAuth flow, connection status, disconnect, and pending restore detection.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.services.google_drive_service import GoogleDriveService

router = APIRouter()


class OAuthCredentials(BaseModel):
    """Google OAuth client credentials for setup."""

    client_id: str
    client_secret: str


class GoogleStatus(BaseModel):
    """Google account connection status."""

    configured: bool
    connected: bool
    email: str | None = None
    avatar_url: str | None = None


class PendingRestore(BaseModel):
    """Whether a cloud backup is available for restore on a fresh install."""

    available: bool
    latest_backup_date: str | None = None


@router.post("/setup")
def save_oauth_credentials(creds: OAuthCredentials):
    """Save Google OAuth client credentials to keyring."""
    service = GoogleDriveService()
    service.save_oauth_credentials(creds.client_id, creds.client_secret)
    return {"status": "configured"}


def _get_callback_uri(request: Request) -> str:
    """Build the OAuth callback URI from the current request's host."""
    return f"{request.base_url}api/google/callback".rstrip("/")


@router.get("/auth-url")
def get_auth_url(request: Request):
    """Generate Google OAuth authorization URL."""
    service = GoogleDriveService()
    try:
        url = service.get_auth_url(redirect_uri=_get_callback_uri(request))
    except ValueError as e:
        from backend.errors import ValidationException

        raise ValidationException(str(e))
    return {"url": url}


@router.get("/callback")
def oauth_callback(code: str, request: Request):
    """Handle Google OAuth callback — exchange code for tokens, redirect to frontend."""
    service = GoogleDriveService()
    service.exchange_code(code, redirect_uri=_get_callback_uri(request))

    from backend.utils.backup import is_db_empty

    has_pending = False
    if is_db_empty():
        backups = service.list_backups()
        has_pending = len(backups) > 0

    # Redirect to frontend on the same host, default port 5173
    frontend_url = f"http://{request.url.hostname}:5173/?google_connected=true"
    if has_pending:
        frontend_url += "&pending_restore=true"
    return RedirectResponse(url=frontend_url)


@router.get("/status", response_model=GoogleStatus)
def get_status():
    """Get Google account connection status."""
    service = GoogleDriveService()
    status = service.get_status()
    return GoogleStatus(
        configured=service.is_configured(),
        connected=status["connected"],
        email=status.get("email"),
        avatar_url=status.get("avatar_url"),
    )


@router.post("/disconnect")
def disconnect():
    """Disconnect Google account — revoke token and remove from keyring."""
    service = GoogleDriveService()
    service.disconnect()

    from backend.database import get_backup_scheduler

    scheduler = get_backup_scheduler()
    if scheduler:
        scheduler.cancel()

    return {"status": "disconnected"}


@router.get("/pending-restore", response_model=PendingRestore)
def check_pending_restore():
    """Check if a cloud backup is available for restore on a fresh install."""
    from backend.utils.backup import is_db_empty

    service = GoogleDriveService()
    if not service.is_connected() or not is_db_empty():
        return PendingRestore(available=False)

    backups = service.list_backups()
    if not backups:
        return PendingRestore(available=False)

    return PendingRestore(
        available=True,
        latest_backup_date=backups[0].get("createdTime"),
    )
