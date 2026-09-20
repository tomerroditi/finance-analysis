"""Tests for the scrape-history endpoints that work without the scraper.

These live in their own router (``routes/scraping_readonly.py``) so they stay
mounted where Playwright is absent. ``backend/main.py`` mounts the scraper's
own router inside ``try/except ImportError: pass``, so a route that sits there
silently disappears on serverless rather than failing loudly.
"""

from unittest.mock import MagicMock, patch


class TestLastScrapesRoute:
    """GET /api/scraping/last-scrapes."""

    def test_returns_the_history_service_rows(self, test_client):
        """The route is a thin pass-through over ScrapingHistoryService."""
        rows = [
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Main Account",
                "last_scrape_date": "2026-09-01T08:30:00",
            }
        ]
        instance = MagicMock()
        instance.get_last_scrape_dates.return_value = rows

        with patch(
            "backend.routes.scraping_readonly.ScrapingHistoryService",
            lambda db: instance,
        ):
            response = test_client.get("/api/scraping/last-scrapes")

        assert response.status_code == 200
        assert response.json() == rows

    def test_no_configured_accounts_is_an_empty_list(self, test_client):
        """Nothing connected answers 200 with [], not an error."""
        instance = MagicMock()
        instance.get_last_scrape_dates.return_value = []

        with patch(
            "backend.routes.scraping_readonly.ScrapingHistoryService",
            lambda db: instance,
        ):
            response = test_client.get("/api/scraping/last-scrapes")

        assert response.status_code == 200
        assert response.json() == []

    def test_the_route_is_served_by_the_readonly_router(self, test_client):
        """Guards the mount, not just the handler.

        The path must resolve to the module that has no scraper import — if
        it ever drifts back into ``routes/scraping.py``, it disappears again
        on any deployment without Playwright, and this is the only thing that
        would notice.
        """
        instance = MagicMock()
        instance.get_last_scrape_dates.return_value = []

        with patch(
            "backend.routes.scraping_readonly.ScrapingHistoryService",
            lambda db: instance,
        ):
            test_client.get("/api/scraping/last-scrapes")

        instance.get_last_scrape_dates.assert_called_once()
