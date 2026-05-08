"""Version + platform info route.

Used by the frontend to show the current version on the Settings → About
panel and to decide whether to show macOS-only UI (the in-app
``Uninstall…`` button). Lightweight and side-effect-free, so it can be
called on app mount without auth concerns.
"""

import sys

from fastapi import APIRouter
from pydantic import BaseModel

from backend.utils.version import get_app_version

router = APIRouter()


class VersionInfo(BaseModel):
    """Process-level version + platform identity for the running backend."""

    version: str
    platform: str


@router.get("", response_model=VersionInfo)
def get_version() -> VersionInfo:
    """Return the running backend version and platform identifier."""
    return VersionInfo(version=get_app_version(), platform=sys.platform)
