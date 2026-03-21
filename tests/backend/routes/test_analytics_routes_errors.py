"""Tests for error/negative paths in the /api/analytics API endpoints."""

from unittest.mock import patch, MagicMock

import pytest


class TestAnalyticsRoutesErrors:
    """Tests for analytics endpoints with invalid inputs and error conditions."""

    def test_get_overview_internal_error(self, test_client):
        """Verify that RuntimeError propagates when AnalysisService.get_overview fails.

        Patches the AnalysisService to simulate an unexpected internal error
        during the overview aggregation.
        """
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_overview.side_effect = RuntimeError("DB connection lost")
            with pytest.raises(RuntimeError, match="DB connection lost"):
                test_client.get("/api/analytics/overview")

    def test_get_net_balance_over_time_internal_error(self, test_client):
        """Verify that RuntimeError propagates when net balance computation fails.

        The analytics routes do not wrap service calls in try/except, so
        internal errors propagate through the test client.
        """
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_net_balance_over_time.side_effect = RuntimeError(
                "Aggregation failed"
            )
            with pytest.raises(RuntimeError, match="Aggregation failed"):
                test_client.get("/api/analytics/net-balance-over-time")

    def test_get_income_expenses_over_time_internal_error(self, test_client):
        """Verify that RuntimeError propagates when income/expenses computation fails."""
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_income_expenses_over_time.side_effect = RuntimeError(
                "Computation error"
            )
            with pytest.raises(RuntimeError, match="Computation error"):
                test_client.get("/api/analytics/income-expenses-over-time")

    def test_get_expenses_by_category_internal_error(self, test_client):
        """Verify that RuntimeError propagates when category breakdown fails."""
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_expenses_by_category.side_effect = RuntimeError(
                "Category aggregation failed"
            )
            with pytest.raises(RuntimeError, match="Category aggregation failed"):
                test_client.get("/api/analytics/by-category")

    def test_get_net_worth_over_time_internal_error(self, test_client):
        """Verify that RuntimeError propagates when net worth computation fails."""
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_net_worth_over_time.side_effect = RuntimeError(
                "Net worth failed"
            )
            with pytest.raises(RuntimeError, match="Net worth failed"):
                test_client.get("/api/analytics/net-worth-over-time")

    def test_get_monthly_expenses_internal_error(self, test_client):
        """Verify that RuntimeError propagates when monthly expenses computation fails."""
        with patch("backend.routes.analytics.AnalysisService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_monthly_expenses.side_effect = RuntimeError(
                "Monthly expenses failed"
            )
            with pytest.raises(RuntimeError, match="Monthly expenses failed"):
                test_client.get("/api/analytics/monthly-expenses")

    def test_get_expenses_by_category_empty_returns_empty(self, test_client):
        """Verify by-category endpoint returns empty list with no data.

        When the database has no transactions, the service returns an
        empty list rather than the usual dict structure.
        """
        response = test_client.get("/api/analytics/by-category")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_get_net_balance_over_time_empty(self, test_client):
        """Verify net-balance-over-time returns empty list with no data."""
        response = test_client.get("/api/analytics/net-balance-over-time")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_income_expenses_over_time_empty(self, test_client):
        """Verify income-expenses-over-time raises KeyError with no data.

        The service accesses ``df['date']`` without guarding against an
        empty DataFrame, so an empty database causes an internal error.
        """
        with pytest.raises(KeyError):
            test_client.get("/api/analytics/income-expenses-over-time")

    def test_get_net_worth_over_time_empty(self, test_client):
        """Verify net-worth-over-time returns empty list with no data."""
        response = test_client.get("/api/analytics/net-worth-over-time")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_monthly_expenses_empty(self, test_client):
        """Verify monthly-expenses returns empty structure with no data."""
        response = test_client.get("/api/analytics/monthly-expenses")
        assert response.status_code == 200
        data = response.json()
        assert "months" in data
        assert data["months"] == []
