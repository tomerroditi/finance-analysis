"""
Testing / development utility routes.

Demo Mode is per-client: a client declares it with the ``X-FAD-Demo``
request header and the backend keeps no per-client state. These routes
therefore do not *switch* anything — they only manage the demo database's
lifecycle and report whether the deployment pins the mode.
"""

import os

from fastapi import APIRouter, Header, HTTPException

from backend import demo_sessions
from backend.config import AppConfig
from backend.demo_setup import (
    build_demo_database,
    demo_database_exists,
    sync_demo_schema,
)
from backend.utils import auth

router = APIRouter()


@router.post("/demo/prepare")
def prepare_demo() -> dict[str, str | bool]:
    """Build the demo database if it is not already present.

    Idempotent. A client switching Demo Mode on calls this; it deliberately
    does **not** rebuild an existing demo database, because another client
    may be browsing it — an existing one only has its schema brought up to
    date, which keeps its data.

    Returns
    -------
    dict
        ``{"status": "success", "created": bool}`` — ``created`` reports
        whether this call actually built the database.
    """
    if AppConfig._forced_mode is not None:
        return {"status": "success", "created": False}

    if demo_database_exists():
        sync_demo_schema()
        return {"status": "success", "created": False}

    build_demo_database()
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

    build_demo_database()
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
    if not auth.token_matches(auth.extract_bearer_token(authorization), secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"deleted": demo_sessions.get_store().prune()}


@router.get("/demo_mode_status")
def get_demo_mode_status() -> dict[str, bool]:
    """Report this request's demo mode and whether the deployment pins it.

    Returns
    -------
    dict
        ``{"demo_mode": bool, "forced": bool, "sandboxed": bool, "durable":
        bool, "blob_configured": bool}``. When ``forced`` is true the deployment ignores
        ``X-FAD-Demo`` and the client cannot opt out — this is how the
        shared Vercel instance advertises itself. ``sandboxed`` is true when
        this request was served from the caller's private per-visitor copy
        of the demo database, and ``durable`` when that copy is mirrored to
        Blob storage rather than living only on this instance.
        ``blob_configured`` reports the deployment's Blob wiring regardless
        of the caller, so an operator can check it with a bare ``curl``
        (see :mod:`backend.demo_sessions`).
    """
    sandboxed = AppConfig().get_demo_session() is not None
    blob_configured = demo_sessions.get_store().durable
    return {
        "demo_mode": AppConfig().is_demo_mode,
        "forced": AppConfig._forced_mode is not None,
        "sandboxed": sandboxed,
        "durable": sandboxed and blob_configured,
        "blob_configured": blob_configured,
    }
