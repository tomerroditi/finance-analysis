"""
Testing / development utility routes.

Demo Mode is per-client: a client declares it with the ``X-FAD-Demo``
request header and the backend keeps no per-client state. These routes
therefore do not *switch* anything — they only manage the demo database's
lifecycle and report whether the deployment pins the mode.
"""

import os

from fastapi import APIRouter

from backend import database
from backend.config import AppConfig
from backend.database import get_db_context
from backend.demo_setup import DEMO_REFERENCE_DATE, prepare_demo_database
from backend.services.credentials_service import CredentialsService
from backend.services.tagging_service import CategoriesTagsService

router = APIRouter()

# Re-exported for backwards compatibility with tests/integrations that
# import this constant from the route module.
__all__ = ["DEMO_REFERENCE_DATE", "router"]


def _demo_db_exists() -> bool:
    """Return ``True`` when the demo database file is already on disk.

    Returns
    -------
    bool
        Whether the demo-mode database path exists.
    """
    config = AppConfig()
    token = config.set_demo_mode(True)
    try:
        return os.path.exists(config.get_db_path())
    finally:
        config.reset_demo_mode(token)


def _build_demo_database() -> None:
    """Copy the frozen snapshot into place and seed demo credentials.

    Forces demo context for its own duration rather than trusting the
    caller's header, so the snapshot can never be copied over the real
    database.
    """
    config = AppConfig()
    token = config.set_demo_mode(True)
    try:
        database.reset_engines()
        CredentialsService.clear_cache()
        CategoriesTagsService.clear_cache()

        prepare_demo_database()

        with get_db_context() as demo_db:
            CredentialsService(demo_db).seed_demo_credentials()
    finally:
        config.reset_demo_mode(token)


@router.post("/demo/prepare")
def prepare_demo() -> dict[str, str | bool]:
    """Build the demo database if it is not already present.

    Idempotent. A client switching Demo Mode on calls this; it deliberately
    does **not** rebuild an existing demo database, because another client
    may be browsing it. Use ``/demo/reset`` for a deliberate rebuild.

    Returns
    -------
    dict
        ``{"status": "success", "created": bool}`` — ``created`` reports
        whether this call actually built the database.
    """
    if AppConfig._forced_mode is not None:
        return {"status": "success", "created": False}

    if _demo_db_exists():
        return {"status": "success", "created": False}

    _build_demo_database()
    return {"status": "success", "created": True}


@router.post("/demo/reset")
def reset_demo() -> dict[str, str]:
    """Rebuild the demo database from the frozen snapshot, unconditionally.

    Discards every change made in Demo Mode by every client and re-anchors
    all dates to today.

    Returns
    -------
    dict
        ``{"status": "success"}``.
    """
    if AppConfig._forced_mode is not None:
        return {"status": "success"}

    _build_demo_database()
    return {"status": "success"}


@router.get("/demo_mode_status")
def get_demo_mode_status() -> dict[str, bool]:
    """Report this request's demo mode and whether the deployment pins it.

    Returns
    -------
    dict
        ``{"demo_mode": bool, "forced": bool}``. When ``forced`` is true the
        deployment ignores ``X-FAD-Demo`` and the client cannot opt out —
        this is how the shared Vercel instance advertises itself.
    """
    return {
        "demo_mode": AppConfig().is_demo_mode,
        "forced": AppConfig._forced_mode is not None,
    }
