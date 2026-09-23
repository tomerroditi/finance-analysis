"""
Unit tests for ScrapingHistory ORM model.
"""

from sqlalchemy.orm import Session

from backend.models.scraping import ScrapingHistory


class TestScrapingHistory:
    """Tests for ScrapingHistory model."""

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
