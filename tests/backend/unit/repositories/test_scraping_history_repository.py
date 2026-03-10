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


class TestScrapingHistoryRepositoryEnsureTable:
    """Tests for _ensure_table_exists stub."""

    def test_ensure_table_exists_is_noop(self, db_session: Session):
        """Verify _ensure_table_exists runs without error as an empty stub."""
        repo = ScrapingHistoryRepository(db_session)
        result = repo._ensure_table_exists()
        assert result is None


class TestScrapingHistoryRepositoryUpdateStatus:
    """Tests for update_status method."""

    def test_update_status_changes_status(self, db_session: Session):
        """Verify update_status transitions a record from one status to another."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            "banks", "hapoalim", "Checking", date(2024, 3, 1),
            status=repo.WAITING_FOR_2FA,
        )

        assert repo.get_scraping_status(scrape_id) == "waiting_for_2fa"

        repo.update_status(scrape_id, repo.IN_PROGRESS)

        assert repo.get_scraping_status(scrape_id) == "in_progress"

    def test_update_status_to_success(self, db_session: Session):
        """Verify update_status can set status to success."""
        repo = ScrapingHistoryRepository(db_session)
        scrape_id = repo.record_scrape_start(
            "credit_cards", "isracard", "Main Card", date(2024, 3, 1),
        )

        repo.update_status(scrape_id, repo.SUCCESS)

        assert repo.get_scraping_status(scrape_id) == "success"


class TestScrapingHistoryRepositoryClearOldRecords:
    """Tests for clear_old_records method."""

    def test_clear_old_records_removes_old_entries(self, db_session: Session):
        """Verify records older than the cutoff are deleted."""
        from datetime import datetime, timedelta

        from backend.models.scraping import ScrapingHistory

        repo = ScrapingHistoryRepository(db_session)

        old_record = ScrapingHistory(
            service_name="banks",
            provider_name="hapoalim",
            account_name="Checking",
            date=(datetime.now() - timedelta(days=60)).isoformat(),
            status=repo.SUCCESS,
            start_date="2024-01-01",
        )
        recent_record = ScrapingHistory(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="Main Card",
            date=datetime.now().isoformat(),
            status=repo.SUCCESS,
            start_date="2024-03-01",
        )
        db_session.add_all([old_record, recent_record])
        db_session.commit()

        repo.clear_old_records(days_to_keep=30)

        history = repo.get_scraping_history()
        assert len(history) == 1
        assert history.iloc[0]["account_name"] == "Main Card"

    def test_clear_old_records_keeps_recent(self, db_session: Session):
        """Verify recent records are not deleted."""
        repo = ScrapingHistoryRepository(db_session)

        repo.record_scrape_start("banks", "hapoalim", "Checking", date(2024, 3, 1))
        repo.record_scrape_start("credit_cards", "isracard", "Card1", date(2024, 3, 1))

        repo.clear_old_records(days_to_keep=30)

        history = repo.get_scraping_history()
        assert len(history) == 2
