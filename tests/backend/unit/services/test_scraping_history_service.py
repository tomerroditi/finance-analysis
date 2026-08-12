"""Tests for ScrapingHistoryService.

Split out of ``ScrapingService`` so the read-only "when did each account last
sync?" query has no dependency on the scraper framework — that is what keeps it
available on deployments without Playwright (see
``tests/backend/routes/test_scraping_readonly_route.py``).
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.scraping_history_service import ScrapingHistoryService


@pytest.fixture
def service():
    """A ScrapingHistoryService with both repositories mocked."""
    with patch(
        "backend.services.scraping_history_service.ScrapingHistoryRepository"
    ) as MockHistoryRepo, patch(
        "backend.services.scraping_history_service.CredentialsRepository"
    ) as MockCredsRepo:
        svc = ScrapingHistoryService(MagicMock())
        svc.scraping_history_repo = MockHistoryRepo.return_value
        svc.credentials_repo = MockCredsRepo.return_value
    return svc


class TestGetLastScrapeDates:
    """One record per configured account, whether or not it ever scraped."""

    def test_returns_a_record_per_configured_account(self, service):
        """Every account is reported, with None for one that never succeeded."""
        service.credentials_repo.list_accounts.return_value = [
            {"service": "credit_cards", "provider": "isracard", "account_name": "Main"},
            {"service": "banks", "provider": "hapoalim", "account_name": "Checking"},
        ]
        service.scraping_history_repo.get_last_successful_scrape_date.side_effect = [
            "2026-02-18",
            None,
        ]

        result = service.get_last_scrape_dates()

        assert result == [
            {
                "service": "credit_cards",
                "provider": "isracard",
                "account_name": "Main",
                "last_scrape_date": "2026-02-18",
            },
            {
                "service": "banks",
                "provider": "hapoalim",
                "account_name": "Checking",
                "last_scrape_date": None,
            },
        ]

    def test_empty_when_no_accounts_are_configured(self, service):
        """A fresh install has no accounts and must not error."""
        service.credentials_repo.list_accounts.return_value = []

        assert service.get_last_scrape_dates() == []
        service.scraping_history_repo.get_last_successful_scrape_date.assert_not_called()

    def test_looks_up_history_per_account_identity(self, service):
        """The lookup is keyed by service + provider + account, not name alone.

        Two accounts can share a name across providers; keying on the full
        identity is what makes the fixture's history line up with its
        credentials.
        """
        service.credentials_repo.list_accounts.return_value = [
            {"service": "banks", "provider": "leumi", "account_name": "Savings Account"},
        ]
        service.scraping_history_repo.get_last_successful_scrape_date.return_value = None

        service.get_last_scrape_dates()

        service.scraping_history_repo.get_last_successful_scrape_date.assert_called_once_with(
            "banks", "leumi", "Savings Account"
        )
