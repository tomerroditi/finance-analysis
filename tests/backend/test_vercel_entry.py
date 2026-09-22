"""Tests for the Vercel serverless entry point (index.py).

Vercel's FastAPI runtime auto-detects a module-level ``app`` binding as the
ASGI application. If that binding is accidentally removed (e.g. a lint
cleanup flags the import as unused), preview and production deployments
fail. This test enforces the contract.
"""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

# One worker runs the whole module so the shared probe subprocess runs once.
pytestmark = pytest.mark.xdist_group("vercel_entry")

_ENTRY_PROBE = """
import json, os, sqlite3, sys, threading
sys.modules["keyring"] = None
import index
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import demo_sessions
from backend.config import AppConfig
from backend.demo_sessions import DemoSessionStore

seen = []
t = threading.Thread(target=lambda: seen.append(AppConfig().is_demo_mode))
t.start(); t.join()
template = DemoSessionStore.template_path()
allocations = 0
if os.path.exists(template):
    c = sqlite3.connect(template)
    allocations = c.execute("SELECT COUNT(*) FROM savings_goal_allocations").fetchone()[0]
    c.close()

sid = sys.argv[1]
client = TestClient(index.app)
h = {"X-FAD-Demo-Session": sid}
status = client.get("/api/testing/demo_mode_status", headers=h)
categories = client.get("/api/tagging/categories", headers=h)
db = DemoSessionStore.local_db_path(sid)
db_created = os.path.exists(db)
reset = client.post("/api/testing/demo/reset", headers=h)

print(json.dumps({
    "app_is_fastapi": isinstance(index.app, FastAPI),
    "demo_mode_seen_by_thread": seen,
    "forced_mode": AppConfig._forced_mode,
    "sessions_enabled": demo_sessions.sessions_enabled(),
    "template_allocations": allocations,
    "status_code": status.status_code,
    "status": status.json(),
    "categories_code": categories.status_code,
    "categories": bool(categories.json()),
    "db_path": db,
    "db_created": db_created,
    "reset_code": reset.status_code,
    "db_after_reset": os.path.exists(db),
}))
"""


@pytest.fixture(scope="module")
def vercel_entry() -> dict:
    """Import ``index.py`` once in a subprocess shaped like the Vercel function.

    ``keyring`` is made unimportable and ``BLOB_READ_WRITE_TOKEN`` is blank,
    exactly as in a deployment without a Blob store (a developer's real token
    would otherwise flip the branch under test). A subprocess keeps the env
    vars and the process-wide demo-mode pin out of the pytest session, and a
    single one is shared because each cold import of the app costs ~2 s.

    Returns
    -------
    dict
        The probe's JSON facts plus the subprocess ``stderr``.
    """
    project_root = Path(__file__).resolve().parents[2]
    # index.py hardcodes FAD_USER_DIR=/tmp/finance-analysis, so the sandbox
    # directory outlives the run. A fresh id keeps a sandbox an earlier run
    # left behind from being silently reused, and it is removed again below.
    session_id = f"visitor-{uuid.uuid4().hex}"
    sandbox_dir = Path("/tmp/finance-analysis/demo_env/sessions") / session_id
    try:
        result = subprocess.run(
            [sys.executable, "-c", _ENTRY_PROBE, session_id],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "BLOB_READ_WRITE_TOKEN": ""},
            check=False,
        )
    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
    assert result.returncode == 0, result.stderr[-3000:]
    facts = json.loads(result.stdout.strip().splitlines()[-1])
    facts["session_id"] = session_id
    facts["stderr"] = result.stderr
    return facts


class TestVercelEntry:
    """Tests protecting the ``index.app`` contract relied on by Vercel."""

    def test_index_exposes_app_as_fastapi_instance(self, vercel_entry):
        """Verify ``import index`` produces a FastAPI ``app`` attribute.

        Vercel's runtime auto-detects the module-level ``app`` binding; if a
        lint cleanup drops it, deployments fail.
        """
        assert vercel_entry["app_is_fastapi"] is True


class TestVercelForcesDemoMode:
    """Tests that the serverless entry point pins demo mode process-wide."""

    def test_entry_pins_demo_mode_for_every_thread(self, vercel_entry):
        """Verify importing index.py leaves demo mode on for all threads.

        A contextvar set at import time would not reach the threads that
        serve requests, so every Vercel request would silently fall back to
        real mode against an empty database. Asserting from a worker thread
        is what distinguishes a process-wide pin from a context-local flag.
        """
        assert vercel_entry["demo_mode_seen_by_thread"] == [True]
        assert vercel_entry["forced_mode"] is True
        assert vercel_entry["sessions_enabled"] is True
        assert vercel_entry["template_allocations"] > 0, (
            "template missing or has no pre-computed allocations"
        )


class TestVercelWithoutKeyring:
    """Tests for the serverless runtime, where ``keyring`` is not installed."""

    def test_sandboxed_request_and_testing_routes_work_without_keyring(
        self, vercel_entry
    ):
        """Verify a sandboxed demo request and the demo routes survive a missing keyring.

        ``credentials_service`` imports ``keyring`` at module load. Two
        things must not depend on that import succeeding: seeding a visitor
        sandbox (the cache-clearing helper reaches for the credentials
        cache), and mounting ``/api/testing`` (its top-level import used to
        drag credentials_service in, so ``main.py`` silently skipped the
        router on Vercel and demo reset 404'd in production).
        """
        assert vercel_entry["status_code"] == 200, vercel_entry["status"]
        assert vercel_entry["status"]["sandboxed"] is True
        assert vercel_entry["categories_code"] == 200
        assert vercel_entry["categories"], "sandbox served no categories"
        assert vercel_entry["db_created"], vercel_entry["db_path"]
        assert "sessions" in vercel_entry["db_path"]
        assert vercel_entry["session_id"] in vercel_entry["db_path"]
        assert vercel_entry["reset_code"] == 200
        assert vercel_entry["db_after_reset"], (
            "reset left the sandbox without a database"
        )


class TestVercelBlobWiringIsVisible:
    """Tests that a deployment without a Blob store says so at cold start."""

    def test_missing_blob_token_logs_a_warning_and_reports_not_configured(
        self, vercel_entry
    ):
        """Verify the non-durable state is loud, not silent.

        Without ``BLOB_READ_WRITE_TOKEN`` a visitor's edits live only on the
        instance that served them. That was invisible until #268: the entry
        point now logs a WARNING naming the remedy and
        ``demo_mode_status.blob_configured`` answers a bare curl.
        """
        assert vercel_entry["status"]["blob_configured"] is False
        assert "BLOB_READ_WRITE_TOKEN is not set" in vercel_entry["stderr"]


class TestVercelCronDeclarations:
    """Tests that every cron declared in ``vercel.json`` hits a real route."""

    def test_declared_cron_paths_are_mounted_get_routes(self):
        """Verify a renamed route cannot silently orphan the prune cron.

        Vercel invokes a cron path with a plain GET and nothing in the
        deployment complains when it 404s — stale visitor sandboxes would
        just accumulate in the Blob store forever.
        """
        from backend.main import app

        project_root = Path(__file__).resolve().parents[2]
        config = json.loads((project_root / "vercel.json").read_text())
        declared = [cron["path"] for cron in config.get("crons", [])]
        # The OpenAPI schema is the flattened view of what is actually
        # mounted (``app.routes`` holds un-expanded router wrappers).
        mounted = app.openapi()["paths"]

        assert declared, "vercel.json declares no crons"
        for path in declared:
            assert path in mounted, f"{path} is not a mounted route"
            assert "get" in mounted[path], f"{path} does not answer GET"
