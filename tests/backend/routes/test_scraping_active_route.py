"""Tests for ``GET /api/scraping/active`` — the UI's in-flight scrape roster.

The Data Sources page keeps its scraping state in a React hook that is torn
down whenever the user navigates away, so a running scrape used to vanish from
the UI on the way back. This route lets the client re-learn what is still
live from ``_active_scrapers``, which is the only place that knows.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.scraper.adapter import _active_scrapers


def _adapter(process_id: int, demo_mode: bool, account: str) -> MagicMock:
    """Build a stand-in adapter with just the fields the route reads."""
    adapter = MagicMock()
    adapter.process_id = process_id
    adapter.demo_mode = demo_mode
    adapter.service_name = "banks"
    adapter.provider_name = "onezero"
    adapter.account_name = account
    return adapter


@pytest.fixture
def clean_registry():
    """Restore ``_active_scrapers`` so a test can't leak into its neighbours."""
    saved = dict(_active_scrapers)
    _active_scrapers.clear()
    yield _active_scrapers
    _active_scrapers.clear()
    _active_scrapers.update(saved)


class TestActiveScrapesRoute:
    """The route reports live scrapes, scoped to the caller's demo mode."""

    def test_returns_empty_list_when_nothing_is_running(
        self, test_client, clean_registry
    ):
        """No live adapters means no in-flight scrapes to restore."""
        response = test_client.get("/api/scraping/active")
        assert response.status_code == 200
        assert response.json() == []

    def test_reports_a_live_scrape_with_its_account_identity(
        self, test_client, clean_registry
    ):
        """The client needs process_id + service/provider/account to match a card."""
        clean_registry[(False, "banks", "onezero", "Acc")] = _adapter(
            42, demo_mode=False, account="Acc"
        )

        response = test_client.get("/api/scraping/active")

        assert response.status_code == 200
        assert response.json() == [
            {
                "process_id": 42,
                "service": "banks",
                "provider": "onezero",
                "account_name": "Acc",
                # No history row exists for this id, so the service falls back
                # to in_progress rather than emitting a null status.
                "status": "in_progress",
            }
        ]

    def test_reports_the_recorded_status_when_one_exists(
        self, test_client, clean_registry
    ):
        """A scraper parked on its OTP must come back as waiting_for_2fa."""
        clean_registry[(False, "banks", "onezero", "Acc")] = _adapter(
            42, demo_mode=False, account="Acc"
        )

        with patch(
            "backend.services.scraping_service.ScrapingHistoryRepository"
        ) as repo_cls:
            repo_cls.return_value.get_scraping_status.return_value = (
                "waiting_for_2fa"
            )
            repo_cls.return_value.IN_PROGRESS = "in_progress"
            response = test_client.get("/api/scraping/active")

        assert response.json()[0]["status"] == "waiting_for_2fa"

    def test_demo_client_does_not_see_a_real_mode_scrape(
        self, test_client, clean_registry
    ):
        """Mode isolation: a demo client must not be handed a real process_id.

        ``process_id`` is a per-database autoincrement, so leaking one across
        modes would let a demo client poll — or abort — a real scrape.
        """
        clean_registry[(False, "banks", "onezero", "Real")] = _adapter(
            1, demo_mode=False, account="Real"
        )
        clean_registry[(True, "banks", "onezero", "Demo")] = _adapter(
            1, demo_mode=True, account="Demo"
        )

        real = test_client.get("/api/scraping/active")
        demo = test_client.get(
            "/api/scraping/active", headers={"X-FAD-Demo": "1"}
        )

        assert [e["account_name"] for e in real.json()] == ["Real"]
        assert [e["account_name"] for e in demo.json()] == ["Demo"]
