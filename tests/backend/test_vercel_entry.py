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
