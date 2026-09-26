"""Tests for error/negative paths in the /api/analytics API endpoints."""

from unittest.mock import MagicMock, patch

import pytest


class TestAnalyticsRoutesErrors:
    """Tests for analytics endpoints with invalid inputs and error conditions."""

    @pytest.mark.parametrize(
        "service_method, path",
        [
            ("get_overview", "/api/analytics/overview"),
            ("get_net_balance_over_time", "/api/analytics/net-balance-over-time"),
            ("get_income_expenses_over_time", "/api/analytics/income-expenses-over-time"),
            ("get_net_worth_over_time", "/api/analytics/net-worth-over-time"),
            ("get_monthly_expenses", "/api/analytics/monthly-expenses"),
        ],
        ids=[
            "overview",
            "net-balance",
            "income-expenses",
            "net-worth",
            "monthly-expenses",
        ],
    )
    def test_internal_error_propagates(self, test_client, service_method, path):
        """Verify a RuntimeError from AnalysisService propagates out of the route.

        The analytics routes do not wrap service calls in try/except, so
        internal errors propagate through the test client.
        """
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            getattr(mock_svc, service_method).side_effect = RuntimeError("Boom")
            with pytest.raises(RuntimeError, match="Boom"):
                test_client.get(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/analytics/net-balance-over-time",
            "/api/analytics/income-expenses-over-time",
            "/api/analytics/net-worth-over-time",
        ],
    )
    def test_time_series_empty_db_returns_empty_list(self, test_client, path):
        """Verify the over-time series endpoints return an empty list with no data."""
        response = test_client.get(path)
        assert response.status_code == 200
        assert response.json() == []

    def test_get_monthly_expenses_empty(self, test_client):
        """Verify monthly-expenses returns empty structure with no data."""
        response = test_client.get("/api/analytics/monthly-expenses")
        assert response.status_code == 200
        data = response.json()
        assert "months" in data
        assert data["months"] == []
