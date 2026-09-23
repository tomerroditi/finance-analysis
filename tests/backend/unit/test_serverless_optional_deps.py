"""The credentials + scrape-history surface must survive a serverless runtime.

Vercel's ``requirements.txt`` deliberately omits ``keyring``, ``cryptography``
and Playwright: the sandbox has no OS keystore, and the hosted demo never
scrapes. ``backend/main.py`` mounts several routers inside
``try/except ImportError: pass``, so a hard import anywhere on those modules'
paths does not fail loudly — the whole route group silently disappears and the
Data Sources page 404s its account list.

That is exactly what used to happen:
``routes/credentials -> credentials_service -> credentials_repository ->
keyring_store -> import keyring``.
"""

import importlib
import sys

import pytest


def _block(monkeypatch, *names):
    """Make ``import <name>`` fail the way it does where it isn't installed."""
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


def _reimport(monkeypatch, module):
    """Re-execute a module's top level under the current import conditions.

    The import also rebinds the module on its parent package, which
    ``sys.modules`` restoration alone does not undo — a later
    ``from backend.utils import crypto`` would get the stripped copy.
    """
    parent_name, _, child = module.rpartition(".")
    parent = importlib.import_module(parent_name)
    if hasattr(parent, child):
        monkeypatch.setattr(parent, child, getattr(parent, child))
    monkeypatch.delitem(sys.modules, module, raising=False)
    return importlib.import_module(module)


class TestKeyringOptional:
    """``keyring_store`` degrades instead of taking the route group with it."""

    def test_module_imports_without_keyring(self, monkeypatch):
        """The import itself must not raise — everything else follows from it."""
        _block(monkeypatch, "keyring", "keyring.errors")
        store = _reimport(monkeypatch, "backend.utils.keyring_store")
        assert store.KEYRING_AVAILABLE is False

    def test_reads_answer_nothing_stored(self, monkeypatch):
        """A secret read degrades to None rather than raising."""
        _block(monkeypatch, "keyring", "keyring.errors")
        store = _reimport(monkeypatch, "backend.utils.keyring_store")
        assert store.get_secret("svc", "name") is None

    def test_deletes_report_nothing_to_delete(self, monkeypatch):
        """Deleting a secret that cannot exist is False, not an exception."""
        _block(monkeypatch, "keyring", "keyring.errors")
        store = _reimport(monkeypatch, "backend.utils.keyring_store")
        assert store.delete_secret("svc", "name") is False

    def test_writes_raise_rather_than_silently_dropping_a_password(
        self, monkeypatch
    ):
        """A write must fail loudly — a lost password is worse than an error."""
        from backend.errors import ValidationException

        _block(monkeypatch, "keyring", "keyring.errors")
        store = _reimport(monkeypatch, "backend.utils.keyring_store")
        with pytest.raises(ValidationException):
            store.set_secret("svc", "name", "hunter2")

    def test_an_explicit_backend_env_var_cannot_conjure_the_package(
        self, monkeypatch
    ):
        """PYTHON_KEYRING_BACKEND normally waives the backend check.

        It must not waive the availability check: naming a backend does not
        install the library, and letting it through would swap a clear error
        for an AttributeError on a None module.
        """
        from backend.errors import ValidationException

        monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")
        _block(monkeypatch, "keyring", "keyring.errors")
        store = _reimport(monkeypatch, "backend.utils.keyring_store")
        with pytest.raises(ValidationException):
            store.ensure_secure_backend()


class TestCryptographyOptional:
    """``crypto`` degrades the same way, and still reads plaintext rows."""

    def test_module_imports_without_cryptography(self, monkeypatch):
        """The import must not raise."""
        _block(monkeypatch, "cryptography", "cryptography.fernet")
        crypto = _reimport(monkeypatch, "backend.utils.crypto")
        assert crypto.CRYPTOGRAPHY_AVAILABLE is False

    def test_plaintext_rows_still_decrypt(self, monkeypatch):
        """The demo database's credential rows are plaintext by design.

        ``decrypt_fields`` passes a non-envelope dict straight through, and
        that path never touches Fernet — which is what makes a credentials
        list possible at all where cryptography is absent.
        """
        _block(monkeypatch, "cryptography", "cryptography.fernet")
        crypto = _reimport(monkeypatch, "backend.utils.crypto")
        assert crypto.decrypt_fields({"username": "demo"}) == {"username": "demo"}

    def test_encrypting_raises_a_readable_error(self, monkeypatch):
        """Writing real credentials without the stack is a clear failure."""
        from backend.errors import ValidationException

        _block(monkeypatch, "cryptography", "cryptography.fernet")
        crypto = _reimport(monkeypatch, "backend.utils.crypto")
        crypto.reset_fernet_cache()
        with pytest.raises(ValidationException):
            crypto.encrypt_fields({"username": "demo"})


class TestScrapeHistoryWithoutTheScraper:
    """``/last-scrapes`` must not depend on Playwright."""

    def test_readonly_route_module_imports_without_the_scraper(self, monkeypatch):
        """The module must not reach the scraper adapter, directly or not."""
        _block(monkeypatch, "playwright", "playwright.async_api")
        module = _reimport(monkeypatch, "backend.routes.scraping_readonly")
        assert module.router is not None

    def test_history_service_does_not_import_the_scraper(self, monkeypatch):
        """Same for the service behind it."""
        _block(monkeypatch, "playwright", "playwright.async_api")
        module = _reimport(monkeypatch, "backend.services.scraping_history_service")
        assert module.ScrapingHistoryService is not None
