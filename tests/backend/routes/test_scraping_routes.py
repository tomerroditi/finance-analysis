"""Tests for the /api/scraping API endpoints."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_scraping(monkeypatch):
    """Mock ScrapingService to avoid real scraping subprocesses."""
    mock_service = MagicMock()
    mock_service.start_scraping_single.return_value = 42
    mock_service.get_scraping_status.return_value = {
        "status": "running",
        "process_id": 42,
    }
    mock_service.submit_2fa_code.return_value = None
    mock_service.abort_scraping_process.return_value = None
    mock_service.get_last_scrape_dates.return_value = []

    monkeypatch.setattr(
        "backend.routes.scraping.ScrapingService",
        lambda db: mock_service,
    )


class TestScrapingRoutes:
    """Tests for scraping API endpoints."""

    def test_start_scraping(self, test_client):
        """POST /api/scraping/start initiates a scraping process."""
        payload = {
            "service": "credit_cards",
            "provider": "isracard",
            "account": "Main Card",
        }
        response = test_client.post("/api/scraping/start", json=payload)
        assert response.status_code == 200
        assert response.json() == 42

    def test_get_scraping_status(self, test_client):
        """GET /api/scraping/status returns scraping status for a process."""
        response = test_client.get("/api/scraping/status?scraping_process_id=42")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["process_id"] == 42

    def test_submit_2fa(self, test_client):
        """POST /api/scraping/2fa submits a 2FA code."""
        payload = {
            "service": "credit_cards",
            "provider": "isracard",
            "account": "Main Card",
            "code": "123456",
        }
        response = test_client.post("/api/scraping/2fa", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_abort_scraping(self, test_client):
        """POST /api/scraping/abort aborts a running scraping process."""
        payload = {"process_id": 42}
        response = test_client.post("/api/scraping/abort", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "aborted"

    def test_get_last_scrapes(self, test_client):
        """GET /api/scraping/last-scrapes returns last scrape dates."""
        response = test_client.get("/api/scraping/last-scrapes")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_start_forwards_force_2fa(self, test_client):
        """POST /api/scraping/start passes force_2fa through to the service."""
        instance = MagicMock()
        instance.start_scraping_single.return_value = 42
        with patch(
            "backend.routes.scraping.ScrapingService", lambda db: instance
        ):
            resp = test_client.post(
                "/api/scraping/start",
                json={
                    "service": "banks",
                    "provider": "onezero",
                    "account": "Acc",
                    "force_2fa": True,
                },
            )
        assert resp.status_code == 200
        assert instance.start_scraping_single.call_args.kwargs["force_2fa"] is True
