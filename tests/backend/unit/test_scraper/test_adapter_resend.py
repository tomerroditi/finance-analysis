"""Tests for adapter-level resend support and pop-by-identity registry hygiene.

Covers:
- ``ScraperAdapter.resend_otp`` delegates to the underlying scraper and
  guards against a resend arriving before ``run()`` built the scraper.
- ``_unregister_from_2fa_waiting`` only evicts a registry entry when it
  still points to ``self`` (pop-by-identity), so an aborted adapter's
  ``finally`` can't drop a freshly-relaunched adapter's single-flight lock.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.errors import EntityNotFoundException
from backend.scraper.adapter import (
    ScraperAdapter,
    _active_scrapers,
    _tfa_scrapers_waiting,
)

DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
DUMMY_START_DATE = __import__("datetime").date(2025, 1, 1)


@pytest.fixture(autouse=True)
def reset_registries():
    """Clear both module-level registries so tests never leak state."""
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()
    yield
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()


def _adapter(process_id: int = 1) -> ScraperAdapter:
    """Build a OneZero adapter for exercising resend / registry behaviour."""
    return ScraperAdapter(
        "banks", "onezero", "Acc",
        DUMMY_CREDENTIALS, DUMMY_START_DATE, process_id,
    )


class TestAdapterResendOtp:
    """ScraperAdapter.resend_otp delegates to the scraper (or guards on None)."""

    def test_scraper_initialised_to_none(self):
        """A fresh adapter has no scraper yet (``_scraper is None``)."""
        adapter = _adapter()
        assert adapter._scraper is None

    def test_resend_delegates_to_scraper(self):
        """resend_otp awaits the underlying scraper's resend_otp exactly once."""
        adapter = _adapter()
        fake_scraper = MagicMock()
        fake_scraper.resend_otp = AsyncMock()
        adapter._scraper = fake_scraper

        asyncio.run(adapter.resend_otp())

        fake_scraper.resend_otp.assert_awaited_once_with()

    def test_resend_before_scraper_ready_raises_not_found(self):
        """A resend that arrives before run() built the scraper raises 404."""
        adapter = _adapter()
        assert adapter._scraper is None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(adapter.resend_otp())


class TestPopByIdentity:
    """_unregister_from_2fa_waiting only removes entries that still point to self.

    Regression for the abort→relaunch race: adapter A is aborted, but by the
    time its run() finally block executes, a fresh adapter B has been
    registered under the same account key. A pop-by-name would evict B and
    silently drop the single-flight lock, letting a duplicate scrape (and a
    duplicate OTP SMS) launch. Pop-by-identity leaves B untouched.
    """

    def test_unregister_leaves_newer_active_adapter(self):
        """A's unregister must not evict B's _active_scrapers entry."""
        name = "banks - onezero - Acc"
        adapter_a = _adapter(process_id=1)
        adapter_b = _adapter(process_id=2)

        # A was registered, then superseded by B under the same key.
        _active_scrapers[name] = adapter_a
        _active_scrapers[name] = adapter_b

        adapter_a._unregister_from_2fa_waiting()

        assert _active_scrapers.get(name) is adapter_b

    def test_unregister_leaves_newer_tfa_adapter(self):
        """A's unregister must not evict B's _tfa_scrapers_waiting entry."""
        name = "banks - onezero - Acc"
        adapter_a = _adapter(process_id=1)
        adapter_b = _adapter(process_id=2)

        _tfa_scrapers_waiting[name] = adapter_a
        _tfa_scrapers_waiting[name] = adapter_b

        adapter_a._unregister_from_2fa_waiting()

        assert _tfa_scrapers_waiting.get(name) is adapter_b

    def test_unregister_removes_own_entry(self):
        """When the entry still points to self, unregister removes it."""
        name = "banks - onezero - Acc"
        adapter_a = _adapter(process_id=1)
        _active_scrapers[name] = adapter_a
        _tfa_scrapers_waiting[name] = adapter_a

        adapter_a._unregister_from_2fa_waiting()

        assert name not in _active_scrapers
        assert name not in _tfa_scrapers_waiting

    def test_unregister_no_entry_does_not_raise(self):
        """Unregister is safe when no entry exists (e.g. already aborted)."""
        adapter_a = _adapter(process_id=1)
        adapter_a._unregister_from_2fa_waiting()  # must not raise
