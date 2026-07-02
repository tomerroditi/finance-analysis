"""Tests for the demo deployment entry point (demo_app.py).

The Cloudflare demo container runs ``uvicorn demo_app:app`` (see
deploy/cloudflare/Dockerfile). If the module-level ``app`` binding is
accidentally removed (e.g. a lint cleanup flags the import as unused), the
deployed demo fails to boot. This test enforces the contract.
"""

import subprocess
import sys
from pathlib import Path


class TestDemoEntry:
    """Tests protecting the ``demo_app.app`` contract relied on by the demo container."""

    def test_demo_app_exposes_app_as_fastapi_instance(self):
        """Verify ``import demo_app`` produces a FastAPI ``app`` attribute.

        Runs in a subprocess so the env vars and demo-mode side effects in
        ``demo_app.py`` do not leak into the current pytest session.
        """
        project_root = Path(__file__).resolve().parents[2]
        script = (
            "import demo_app; "
            "from fastapi import FastAPI; "
            "assert isinstance(demo_app.app, FastAPI), type(demo_app.app)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"demo_app.py no longer exposes a FastAPI `app` binding — the demo "
            f"container will fail to boot.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
