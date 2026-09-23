"""Tests for the _active_scrapers single-flight registry cleanup in run()."""

import asyncio
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.scraper.adapter import (
    ScraperAdapter,
    _active_scrapers,
    _tfa_scrapers_waiting,
    scraper_registry_key,
)

DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
DUMMY_START_DATE = date(2025, 1, 1)


@pytest.fixture(autouse=True)
def reset_registries():
    """Clear both module-level registries so tests never leak state."""
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()
    yield
    _active_scrapers.clear()
    _tfa_scrapers_waiting.clear()


def _adapter(process_id: int = 1) -> ScraperAdapter:
    """Build a non-2FA-provider adapter suitable for exercising run()."""
    return ScraperAdapter(
        "credit_cards", "isracard", "Card1",
        DUMMY_CREDENTIALS, DUMMY_START_DATE, process_id,
    )


_FAILED = SimpleNamespace(success=False, error_message="boom", error_type=None)
_SUCCEEDED = SimpleNamespace(success=True, accounts=[])


def _run_with_scrape_result(adapter: ScraperAdapter, scrape_result) -> None:
    """Drive ``adapter.run()`` against a fake scraper returning ``scrape_result``."""
    fake_scraper = MagicMock()
    fake_scraper.scrape = AsyncMock(return_value=scrape_result)
    fake_scraper.refreshed_otp_long_term_token = None

    fake_scraper_pkg = SimpleNamespace(
        create_scraper=MagicMock(return_value=fake_scraper),
        is_2fa_required=MagicMock(return_value=False),
    )
    fake_base_scraper_mod = SimpleNamespace(ScraperOptions=MagicMock())

    def fake_import(module_name):
        if module_name == "scraper":
            return fake_scraper_pkg
        if module_name == "scraper.base.base_scraper":
            return fake_base_scraper_mod
        raise AssertionError(f"Unexpected import: {module_name}")

    @contextmanager
    def fake_db_context():
        yield MagicMock()

    with patch(
        "backend.scraper.adapter._import_scraper_module",
        side_effect=fake_import,
    ), patch(
        "backend.scraper.adapter.get_db_context",
        side_effect=fake_db_context,
    ), patch(
        "backend.scraper.adapter.ScrapingHistoryRepository",
        return_value=MagicMock(),
    ):
        asyncio.run(adapter.run())


class TestRunPopsActiveScrapers:
    """ScraperAdapter.run()'s finally block removes the active-scraper entry.

    Without this, a completed or failed scrape would leave the account
    permanently locked out of future launches by
    ScrapingService.start_scraping_single's single-flight check.
    """

    @pytest.mark.parametrize(
        "scrape_result,registered",
        [
            pytest.param(_FAILED, True, id="failure"),
            pytest.param(_SUCCEEDED, True, id="success-no-transactions"),
            pytest.param(_FAILED, False, id="already-unregistered"),
        ],
    )
    def test_run_pops_active_scrapers(self, scrape_result, registered):
        """run() leaves no _active_scrapers entry behind, whatever the outcome.

        The unregistered case covers an entry already removed (e.g. by an
        abort): the finally block must not raise on the missing key.
        """
        adapter = _adapter()
        key = scraper_registry_key(False, "credit_cards", "isracard", "Card1")
        if registered:
            _active_scrapers[key] = adapter

        _run_with_scrape_result(adapter, scrape_result)

        assert key not in _active_scrapers
