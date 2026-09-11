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


class TestVercelEntry:
    """Tests protecting the ``index.app`` contract relied on by Vercel."""

    def test_index_exposes_app_as_fastapi_instance(self):
        """Verify ``import index`` produces a FastAPI ``app`` attribute.

        Runs in a subprocess so the env vars and demo-mode side effects in
        ``index.py`` do not leak into the current pytest session.
        """
        project_root = Path(__file__).resolve().parents[2]
        script = (
            "import index; "
            "from fastapi import FastAPI; "
            "assert isinstance(index.app, FastAPI), type(index.app)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"index.py no longer exposes a FastAPI `app` binding — Vercel "
            f"will fail to deploy.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestVercelForcesDemoMode:
    """Tests that the serverless entry point pins demo mode process-wide."""

    def test_entry_pins_demo_mode_for_every_thread(self):
        """Verify importing index.py leaves demo mode on for all threads.

        A contextvar set at import time would not reach the threads that
        serve requests, so every Vercel request would silently fall back to
        real mode against an empty database. Asserting from a worker thread
        is what distinguishes a process-wide pin from a context-local flag.

        Runs in a subprocess so the env vars and demo-mode side effects in
        ``index.py`` do not leak into the current pytest session.
        """
        project_root = Path(__file__).resolve().parents[2]
        script = (
            "import threading; import index; "
            "from backend.config import AppConfig; "
            "seen = []; "
            "t = threading.Thread("
            "    target=lambda: seen.append(AppConfig().is_demo_mode)); "
            "t.start(); t.join(); "
            "assert seen == [True], seen; "
            "assert AppConfig._forced_mode is True, AppConfig._forced_mode; "
            "import os; from backend import demo_sessions; "
            "assert demo_sessions.sessions_enabled(), 'sandboxes off'; "
            "assert os.path.exists(demo_sessions.DemoSessionStore.template_path()), "
            "'template missing'; "
            "import sqlite3; "
            "c = sqlite3.connect(demo_sessions.DemoSessionStore.template_path()); "
            "n = c.execute('SELECT COUNT(*) FROM savings_goal_allocations').fetchone()[0]; "
            "assert n > 0, 'template has no pre-computed allocations'"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


class TestVercelWithoutKeyring:
    """Tests for the serverless runtime, where ``keyring`` is not installed."""

    def test_sandboxed_request_and_testing_routes_work_without_keyring(self):
        """Verify a sandboxed demo request and the demo routes survive a missing keyring.

        ``credentials_service`` imports ``keyring`` at module load. Two
        things must not depend on that import succeeding: seeding a visitor
        sandbox (the cache-clearing helper reaches for the credentials
        cache), and mounting ``/api/testing`` (its top-level import used to
        drag credentials_service in, so ``main.py`` silently skipped the
        router on Vercel and demo reset 404'd in production).

        Runs in a subprocess with ``keyring`` made unimportable, exactly
        like the Vercel function.
        """
        project_root = Path(__file__).resolve().parents[2]
        # index.py hardcodes FAD_USER_DIR=/tmp/finance-analysis, so the
        # sandbox directory outlives the test run. A fresh id per run keeps
        # this from silently reusing (or being broken by) a sandbox an
        # earlier run left behind, and it is removed again below.
        session_id = f"visitor-{uuid.uuid4().hex}"
        sandbox_dir = Path("/tmp/finance-analysis/demo_env/sessions") / session_id
        script = (
            "import sys, os; sys.modules['keyring'] = None; "
            "import index; "
            "from fastapi.testclient import TestClient; "
            f"sid = {session_id!r}; "
            "c = TestClient(index.app); "
            "h = {'X-FAD-Demo-Session': sid}; "
            "r = c.get('/api/testing/demo_mode_status', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text); "
            "assert r.json()['sandboxed'] is True, r.json(); "
            "r = c.get('/api/tagging/categories', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text); "
            "assert r.json(), 'sandbox served no categories'; "
            "from backend.demo_sessions import DemoSessionStore; "
            "db = DemoSessionStore.local_db_path(sid); "
            "assert os.path.exists(db), db; "
            "assert 'sessions' in db and sid in db, db; "
            "r = c.post('/api/testing/demo/reset', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text); "
            "assert os.path.exists(db), 'reset left the sandbox without a database'"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        assert result.returncode == 0, result.stderr[-3000:]


class TestVercelBlobWiringIsVisible:
    """Tests that a deployment without a Blob store says so at cold start."""

    def test_missing_blob_token_logs_a_warning_and_reports_not_configured(self):
        """Verify the non-durable state is loud, not silent.

        Without ``BLOB_READ_WRITE_TOKEN`` a visitor's edits live only on the
        instance that served them. That was invisible until #268: the entry
        point now logs a WARNING naming the remedy and
        ``demo_mode_status.blob_configured`` answers a bare curl.
        """
        project_root = Path(__file__).resolve().parents[2]
        script = (
            "import index; "
            "from fastapi.testclient import TestClient; "
            "r = TestClient(index.app).get('/api/testing/demo_mode_status'); "
            "assert r.json()['blob_configured'] is False, r.json()"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
            # Explicit: a developer with a real token in their shell would
            # otherwise flip the branch under test.
            env={**os.environ, "BLOB_READ_WRITE_TOKEN": ""},
        )
        assert result.returncode == 0, result.stderr[-3000:]
        assert "BLOB_READ_WRITE_TOKEN is not set" in result.stderr


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
