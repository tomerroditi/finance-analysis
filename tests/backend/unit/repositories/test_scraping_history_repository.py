"""
Unit tests for ScrapingHistoryRepository operations.
"""

from datetime import date

from sqlalchemy.orm import Session

from backend.repositories.scraping_history_repository import ScrapingHistoryRepository


class TestScrapingHistoryRepository:
    """Tests for ScrapingHistoryRepository operations."""

    def test_record_scrape_start(self, db_session: Session):
        """Verify recording a scrape start returns an ID."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="Main Card",
            start_date=date(2024, 1, 15),
        )

        assert isinstance(scrape_id, int)
        assert scrape_id > 0

    def test_record_scrape_end_success(self, db_session: Session):
        """Verify recording scrape end with success status."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="Main Card",
            start_date=date(2024, 1, 15),
        )

        repo.record_scrape_end(scrape_id, status=repo.SUCCESS)

        status = repo.get_scraping_status(scrape_id)
        assert status == "success"

    def test_record_scrape_end_failed(self, db_session: Session):
        """Verify recording scrape end with failed status and error message."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            service_name="banks",
            provider_name="hapoalim",
            account_name="Checking",
            start_date=date(2024, 1, 15),
        )

        repo.record_scrape_end(
            scrape_id,
            status=repo.FAILED,
            error_message="Connection timeout",
        )

        status = repo.get_scraping_status(scrape_id)
        assert status == "failed"
        error = repo.get_error_message(scrape_id)
        assert error == "Connection timeout"

    def test_get_scraping_status(self, db_session: Session):
        """Verify getting status by scrape ID."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="Main Card",
            start_date=date(2024, 1, 15),
        )

        status = repo.get_scraping_status(scrape_id)
        assert status == "in_progress"

    def test_get_scraping_status_not_found(self, db_session: Session):
        """Verify None returned for non-existent scrape ID."""
        repo = ScrapingHistoryRepository(db_session)
        status = repo.get_scraping_status(999)
        assert status is None

    def test_get_error_message(self, db_session: Session):
        """Verify getting error message for failed scrape."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="Main Card",
            start_date=date(2024, 1, 15),
        )

        # Initially no error
        assert repo.get_error_message(scrape_id) is None

        repo.record_scrape_end(scrape_id, repo.FAILED, "Invalid password")
        assert repo.get_error_message(scrape_id) == "Invalid password"

    def test_get_scraping_history(self, db_session: Session):
        """Verify getting full history as DataFrame."""
        repo = ScrapingHistoryRepository(db_session)
        repo.record_scrape_start(
            "credit_cards", "isracard", "Card 1", date(2024, 1, 15)
        )
        repo.record_scrape_start(
            "banks", "hapoalim", "Checking", date(2024, 1, 15)
        )

        history = repo.get_scraping_history()
        assert len(history) == 2
        assert "service_name" in history.columns
        assert "status" in history.columns

    def test_get_last_successful_scrape_date(self, db_session: Session):
        """Verify getting last successful scrape date for an account."""
        repo = ScrapingHistoryRepository(db_session)

        # Record a failed scrape first
        id1 = repo.record_scrape_start(
            "credit_cards", "isracard", "Main Card", date(2024, 1, 10)
        )
        repo.record_scrape_end(id1, repo.FAILED, "Error")

        # Then a successful one
        id2 = repo.record_scrape_start(
            "credit_cards", "isracard", "Main Card", date(2024, 1, 15)
        )
        repo.record_scrape_end(id2, repo.SUCCESS)

        result = repo.get_last_successful_scrape_date(
            "credit_cards", "isracard", "Main Card"
        )
        assert result is not None
        assert isinstance(result, str)

    def test_get_last_successful_scrape_date_none(self, db_session: Session):
        """Verify None returned when no successful scrapes exist."""
        repo = ScrapingHistoryRepository(db_session)

        # Only failed scrapes
        id1 = repo.record_scrape_start(
            "credit_cards", "isracard", "Main Card", date(2024, 1, 10)
        )
        repo.record_scrape_end(id1, repo.FAILED, "Error")

        result = repo.get_last_successful_scrape_date(
            "credit_cards", "isracard", "Main Card"
        )
        assert result is None
