"""
Testing / development utility routes.

Demo Mode is per-client: a client declares it with the ``X-FAD-Demo``
request header and the backend keeps no per-client state. These routes
therefore do not *switch* anything — they only manage the demo database's
lifecycle and report whether the deployment pins the mode.
"""

import hmac
import os

from fastapi import APIRouter, Header, HTTPException

from backend import database, demo_sessions
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
    all dates to today. When the request is bound to a per-visitor sandbox
    (the Vercel deployment), only that visitor's copy is discarded and
    re-seeded from the pristine template.

    Returns
    -------
    dict
        ``{"status": "success"}``.
    """
    session_id = AppConfig().get_demo_session()
    if session_id is not None:
        demo_sessions.get_store().reset(session_id)
        return {"status": "success"}

    if AppConfig._forced_mode is not None:
        return {"status": "success"}

    _build_demo_database()
    return {"status": "success"}


@router.get("/demo/prune")
def prune_demo_sessions(
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    """Delete persisted visitor sandboxes that have gone stale.

    Invoked by the Vercel cron declared in ``vercel.json``; Vercel sends
    ``Authorization: Bearer <CRON_SECRET>`` when that variable is set. The
    route is absent (404) unless ``CRON_SECRET`` is configured, so it can
    never be triggered on a deployment that did not opt in.

    Returns
    -------
    dict
        ``{"deleted": n}`` — number of sandbox blobs removed.
    """
    secret = os.environ.get("CRON_SECRET", "")
    if not secret:
        raise HTTPException(status_code=404, detail="Not Found")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"deleted": demo_sessions.get_store().prune()}


@router.get("/demo_mode_status")
def get_demo_mode_status() -> dict[str, bool]:
    """Report this request's demo mode and whether the deployment pins it.

    Returns
    -------
    dict
        ``{"demo_mode": bool, "forced": bool, "sandboxed": bool}``. When
        ``forced`` is true the deployment ignores ``X-FAD-Demo`` and the
        client cannot opt out — this is how the shared Vercel instance
        advertises itself. ``sandboxed`` is true when this request was
        served from the caller's private per-visitor copy of the demo
        database (see :mod:`backend.demo_sessions`).
    """
    return {
        "demo_mode": AppConfig().is_demo_mode,
        "forced": AppConfig._forced_mode is not None,
        "sandboxed": AppConfig().get_demo_session() is not None,
    }
