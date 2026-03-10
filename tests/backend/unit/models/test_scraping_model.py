"""
Unit tests for ScrapingHistory ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.scraping import ScrapingHistory


class TestScrapingHistory:
    """Tests for ScrapingHistory model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert ScrapingHistory.__tablename__ == Tables.SCRAPING_HISTORY.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="hapoalim",
            account_name="main",
            date="2026-01-16T10:30:00",
            status="success",
            start_date="2025-12-01",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.id is not None
        assert history.service_name == "banks"
        assert history.provider_name == "hapoalim"
        assert history.status == "success"

    def test_failed_scraping(self, db_session: Session):
        """Test recording a failed scraping attempt."""
        history = ScrapingHistory(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="personal",
            date="2026-01-16T11:00:00",
            status="failed",
            start_date="2026-01-01",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.status == "failed"

    def test_nullable_start_date(self, db_session: Session):
        """Test that start_date is nullable."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="leumi",
            account_name="investments",
            date="2026-01-16T12:00:00",
            status="success",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.start_date is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="discount",
            account_name="main",
            date="2026-01-16T13:00:00",
            status="success",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert hasattr(history, "created_at")
        assert history.created_at is not None
