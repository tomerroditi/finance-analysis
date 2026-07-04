"""Tests for the _active_scrapers single-flight registry cleanup in run()."""

import asyncio
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.scraper.adapter import ScraperAdapter, _active_scrapers, _tfa_scrapers_waiting

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


class TestRunPopsActiveScrapers:
    """ScraperAdapter.run()'s finally block removes the active-scraper entry.

    Without this, a completed or failed scrape would leave the account
    permanently locked out of future launches by
    ScrapingService.start_scraping_single's single-flight check.
    """

    def test_run_pops_active_scrapers_on_failure(self):
        """A failed scrape still pops its _active_scrapers entry in finally."""
        adapter = _adapter(process_id=101)
        name = "credit_cards - isracard - Card1"
        _active_scrapers[name] = adapter

        fake_scraper = MagicMock()
        fake_scraper.scrape = AsyncMock(
            return_value=SimpleNamespace(
                success=False, error_message="boom", error_type=None,
            )
        )

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

        mock_history_repo = MagicMock()

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
            return_value=mock_history_repo,
        ):
            asyncio.run(adapter.run())

        assert name not in _active_scrapers

    def test_run_pops_active_scrapers_on_success(self):
        """A successful scrape with no transactions also pops its entry."""
        adapter = _adapter(process_id=102)
        name = "credit_cards - isracard - Card1"
        _active_scrapers[name] = adapter

        fake_scraper = MagicMock()
        fake_scraper.scrape = AsyncMock(
            return_value=SimpleNamespace(success=True, accounts=[])
        )
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

        mock_history_repo = MagicMock()

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
            return_value=mock_history_repo,
        ):
            asyncio.run(adapter.run())

        assert name not in _active_scrapers

    def test_run_pops_active_scrapers_even_when_not_registered(self):
        """run() must not raise if the entry is already absent (e.g. aborted)."""
        adapter = _adapter(process_id=103)
        # Deliberately NOT registered in _active_scrapers.

        fake_scraper = MagicMock()
        fake_scraper.scrape = AsyncMock(
            return_value=SimpleNamespace(
                success=False, error_message="boom", error_type=None,
            )
        )

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

        mock_history_repo = MagicMock()

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
            return_value=mock_history_repo,
        ):
            asyncio.run(adapter.run())  # must not raise

        assert "credit_cards - isracard - Card1" not in _active_scrapers
