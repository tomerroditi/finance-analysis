"""Tests for the scraper-free scrape-history route.

``/api/scraping/last-scrapes`` is registered from ``routes/scraping_readonly``
rather than ``routes/scraping`` so it stays mounted where the scraper framework
(Playwright) cannot be installed — the hosted demo. Without it, every source on
that deployment reported "never synced" and the balance-entry affordance stayed
disabled, despite the history being present in the demo database.
"""

from unittest.mock import MagicMock, patch


class TestScrapingReadonlyRoute:
    """The history endpoint answers without touching the scraper stack."""

    def test_last_scrapes_returns_service_records(self, test_client):
        """GET /api/scraping/last-scrapes returns one record per account."""
        instance = MagicMock()
        instance.get_last_scrape_dates.return_value = [
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Main Account",
                "last_scrape_date": "2026-08-11T08:30:00",
            },
        ]
        with patch(
            "backend.routes.scraping_readonly.ScrapingHistoryService",
            lambda db: instance,
        ):
            response = test_client.get("/api/scraping/last-scrapes")

        assert response.status_code == 200
        assert response.json() == [
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Main Account",
                "last_scrape_date": "2026-08-11T08:30:00",
            },
        ]

    def test_last_scrapes_is_served_without_the_scraper_router(self):
        """The route must come from the module that has no scraper import.

        If it drifted back into ``routes/scraping``, it would vanish from every
        deployment lacking Playwright — silently, because ``main.py`` swallows
        that ImportError.
        """
        from backend.routes import scraping, scraping_readonly

        assert "/last-scrapes" in {r.path for r in scraping_readonly.router.routes}
        assert "/last-scrapes" not in {r.path for r in scraping.router.routes}
