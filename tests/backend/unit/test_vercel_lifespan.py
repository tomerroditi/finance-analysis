"""Regression tests for the Vercel serverless application lifespan.

On Vercel, ``requirements.txt`` intentionally omits ``keyring`` — there is no
OS keyring in a serverless sandbox and demo-mode deployments never scrape. The
``lifespan`` in :mod:`backend.main` guards on the ``VERCEL`` env var and yields
early precisely so it never touches keyring-backed code.

PR #156 regressed this: it placed
``from backend.services.scraping_service import set_main_loop`` *above* the
``VERCEL`` guard. ``scraping_service`` imports ``credentials_repository`` which
does ``import keyring`` at module load, so every cold start crashed with
``ModuleNotFoundError: No module named 'keyring'`` → ``FUNCTION_INVOCATION_FAILED``
(HTTP 500) on the production deployment.

This test simulates the serverless runtime (keyring absent) and asserts the
lifespan still starts.
"""

import asyncio
import sys

import pytest
from fastapi import FastAPI

import backend.main as main


class TestVercelLifespanNoKeyring:
    """The VERCEL lifespan path must start without the keyring package."""

    def test_lifespan_starts_without_keyring_on_vercel(self, monkeypatch):
        """Entering the lifespan under VERCEL must not import keyring."""
        monkeypatch.setenv("VERCEL", "1")

        # Make ``import keyring`` fail the way it does in Vercel's runtime,
        # where the package isn't installed.
        monkeypatch.setitem(sys.modules, "keyring", None)
        # Evict the modules whose module-level ``import keyring`` already ran
        # in this process, so any fresh import re-executes that (now failing)
        # import instead of returning the cached module.
        monkeypatch.delitem(
            sys.modules, "backend.services.scraping_service", raising=False
        )
        monkeypatch.delitem(
            sys.modules, "backend.repositories.credentials_repository", raising=False
        )

        # Sanity check: keyring really is unimportable in this simulated runtime.
        with pytest.raises(ModuleNotFoundError):
            import keyring  # noqa: F401

        async def drive():
            async with main.lifespan(FastAPI()):
                return True

        # Reaching the assert means startup succeeded without keyring.
        assert asyncio.run(drive()) is True
