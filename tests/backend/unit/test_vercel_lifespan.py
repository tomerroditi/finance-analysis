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
import builtins
import importlib
import sys

import pytest
from fastapi import FastAPI

import backend.main as main
from backend.errors import ValidationException


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


class TestServerlessReadOnlySurface:
    """Read-only credential + scrape-history APIs must survive a keyring-less runtime.

    The hosted demo has no OS keyring and no ``cryptography``. Both sit on the
    import path of ``backend.routes.credentials``, and ``backend/main.py`` wraps
    that import in ``except ImportError: pass`` — so a hard module-level import
    silently dropped the ENTIRE ``/api/credentials`` surface from the deployed
    app. The Data Sources page then had no account list to render and came up
    permanently empty: exactly the bug this class pins.
    """

    @staticmethod
    def _reimport_without(monkeypatch, blocked: set[str], module: str):
        """Import ``module`` fresh with ``blocked`` top-level packages missing."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.split(".")[0] in blocked:
                raise ImportError(f"simulated missing package: {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        for cached in [m for m in list(sys.modules) if m.split(".")[0] in blocked]:
            monkeypatch.delitem(sys.modules, cached, raising=False)
        for cached in [
            m
            for m in list(sys.modules)
            if m.startswith(("backend.utils.keyring_store", "backend.utils.crypto"))
            or m.startswith("backend.repositories.credentials_repository")
            or m.startswith("backend.services.credentials_service")
            or m.startswith(module)
        ]:
            monkeypatch.delitem(sys.modules, cached, raising=False)
        return importlib.import_module(module)

    def test_credentials_routes_import_without_keyring_or_cryptography(
        self, monkeypatch
    ):
        """The credentials router imports with neither package installed."""
        module = self._reimport_without(
            monkeypatch, {"keyring", "cryptography"}, "backend.routes.credentials"
        )
        paths = {route.path for route in module.router.routes}
        assert "/accounts" in paths

    def test_scrape_history_route_imports_without_playwright(self, monkeypatch):
        """Scrape history is a DB read and must not need the scraper stack.

        ``backend.routes.scraping`` legitimately requires Playwright; the
        read-only history route is split out so "when did this last sync?"
        keeps working where the scraper cannot be installed.
        """
        module = self._reimport_without(
            monkeypatch,
            {"keyring", "cryptography", "playwright"},
            "backend.routes.scraping_readonly",
        )
        paths = {route.path for route in module.router.routes}
        assert "/last-scrapes" in paths

    def test_secret_reads_degrade_and_writes_raise_without_keyring(self, monkeypatch):
        """No keyring: reads report "nothing stored", writes fail loudly.

        A read must not explode (the demo lists accounts whose passwords simply
        aren't there), and a write must never silently drop a real user's
        password.
        """
        store = self._reimport_without(
            monkeypatch, {"keyring"}, "backend.utils.keyring_store"
        )
        assert store.KEYRING_AVAILABLE is False
        assert store.get_secret("svc", "name") is None
        assert store.delete_secret("svc", "name") is False
        with pytest.raises(ValidationException):
            store.set_secret("svc", "name", "value")

    def test_plaintext_fields_decrypt_without_cryptography(self, monkeypatch):
        """Legacy/fixture plaintext rows read back without the crypto stack.

        The demo fixture ships its credential rows plaintext (a committed file
        cannot carry a per-machine key), and the serverless runtime has no
        ``cryptography`` — so the plaintext path must not touch Fernet.
        """
        crypto = self._reimport_without(
            monkeypatch, {"cryptography"}, "backend.utils.crypto"
        )
        assert crypto.CRYPTOGRAPHY_AVAILABLE is False
        assert crypto.decrypt_fields({"userCode": "demo"}) == {"userCode": "demo"}
        with pytest.raises(ValidationException):
            crypto.encrypt_fields({"userCode": "demo"})
