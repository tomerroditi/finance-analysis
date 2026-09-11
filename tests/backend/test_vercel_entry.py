"""Tests for the Vercel serverless entry point (index.py).

Vercel's FastAPI runtime auto-detects a module-level ``app`` binding as the
ASGI application. If that binding is accidentally removed (e.g. a lint
cleanup flags the import as unused), preview and production deployments
fail. This test enforces the contract.
"""

import subprocess
import sys
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
        script = (
            "import sys, tempfile, os; sys.modules['keyring'] = None; "
            "import index; "
            "from fastapi.testclient import TestClient; "
            "c = TestClient(index.app); "
            "h = {'X-FAD-Demo-Session': 'visitor-0123456789abcdef'}; "
            "r = c.get('/api/testing/demo_mode_status', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text); "
            "assert r.json()['sandboxed'] is True, r.json(); "
            "r = c.get('/api/tagging/categories', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text); "
            "r = c.post('/api/testing/demo/reset', headers=h); "
            "assert r.status_code == 200, (r.status_code, r.text)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr[-3000:]
