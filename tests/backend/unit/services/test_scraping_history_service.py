"""Tests for ScrapingHistoryService."""

from unittest.mock import MagicMock

from backend.services.scraping_history_service import ScrapingHistoryService


class TestGetLastScrapeDates:
    """The scrape-history read that the hosted demo depends on.

    This logic lives outside ``ScrapingService`` on purpose: that module
    imports the scraper adapter, and therefore Playwright, which serverless
    deployments do not install. Anything asserted here has to hold without
    the scraper stack.
    """

    @staticmethod
    def _service(accounts, dates):
        """Build a service over stubbed repositories."""
        svc = ScrapingHistoryService(MagicMock())
        svc.credentials_repo = MagicMock()
        svc.credentials_repo.list_accounts.return_value = accounts
        svc.scraping_history_repo = MagicMock()
        svc.scraping_history_repo.get_last_successful_scrape_date.side_effect = (
            lambda s, p, a: dates.get((s, p, a))
        )
        return svc

    def test_pairs_each_configured_account_with_its_last_success(self):
        """Every configured account gets one row carrying its watermark."""
        accounts = [
            {"service": "banks", "provider": "hapoalim", "account_name": "Main"},
            {"service": "credit_cards", "provider": "max", "account_name": "Family"},
        ]
        dates = {
            ("banks", "hapoalim", "Main"): "2026-09-01T08:30:00",
            ("credit_cards", "max", "Family"): "2026-09-02T08:35:00",
        }

        result = self._service(accounts, dates).get_last_scrape_dates()

        assert result == [
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Main",
                "last_scrape_date": "2026-09-01T08:30:00",
            },
            {
                "service": "credit_cards",
                "provider": "max",
                "account_name": "Family",
                "last_scrape_date": "2026-09-02T08:35:00",
            },
        ]

    def test_never_scraped_account_is_listed_with_a_null_date(self):
        """An account with no successful scrape still gets a card, not a gap."""
        accounts = [
            {"service": "banks", "provider": "leumi", "account_name": "Savings"}
        ]

        result = self._service(accounts, {}).get_last_scrape_dates()

        assert result == [
            {
                "service": "banks",
                "provider": "leumi",
                "account_name": "Savings",
                "last_scrape_date": None,
            }
        ]

    def test_no_configured_accounts_yields_no_rows(self):
        """Nothing connected is an empty list, not an error."""
        assert self._service([], {}).get_last_scrape_dates() == []

    def test_scrape_history_is_keyed_by_the_full_account_identity(self):
        """Lookups pass service AND provider AND account, never a bare name.

        Two providers can use the same account name, and the history table
        is keyed on all three.
        """
        accounts = [
            {"service": "banks", "provider": "hapoalim", "account_name": "Main"}
        ]
        svc = self._service(accounts, {})

        svc.get_last_scrape_dates()

        svc.scraping_history_repo.get_last_successful_scrape_date.assert_called_once_with(
            "banks", "hapoalim", "Main"
        )
