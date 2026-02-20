"""Tests for the /api/analytics API endpoints."""

import pytest


class TestAnalyticsRoutes:
    """Tests for analytics API endpoints."""

    def test_get_overview(self, test_client, seed_base_transactions):
        """GET /api/analytics/overview returns overview with financial data."""
        response = test_client.get("/api/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "total_transactions" in data
        assert "total_income" in data
        assert "total_expenses" in data
        assert "net_balance_change" in data
        assert "latest_data_date" in data
        assert data["total_transactions"] == len(seed_base_transactions)
        assert data["total_income"] > 0
        assert data["total_expenses"] > 0

    def test_get_overview_date_filter(self, test_client, seed_base_transactions):
        """GET /api/analytics/overview with date filter narrows results."""
        response = test_client.get(
            "/api/analytics/overview?start_date=2024-01-01&end_date=2024-01-31"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Filtered to January only, so fewer transactions than the full set
        assert data["total_transactions"] < len(seed_base_transactions)
        assert data["total_transactions"] > 0

    def test_get_net_balance_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/net-balance-over-time returns time series data."""
        response = test_client.get("/api/analytics/net-balance-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Each entry should have month, net_change, and cumulative_balance
        entry = data[0]
        assert "month" in entry
        assert "net_change" in entry
        assert "cumulative_balance" in entry

    def test_get_income_expenses_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-expenses-over-time returns income/expense data."""
        response = test_client.get("/api/analytics/income-expenses-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        entry = data[0]
        assert "month" in entry
        assert "income" in entry
        assert "expenses" in entry

    def test_get_expenses_by_category(self, test_client, seed_base_transactions):
        """GET /api/analytics/by-category returns category breakdown."""
        response = test_client.get("/api/analytics/by-category")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "expenses" in data
        assert "refunds" in data
        assert isinstance(data["expenses"], list)
        # Seed data has expense categories like Food, Transport, Entertainment
        assert len(data["expenses"]) > 0
        expense_entry = data["expenses"][0]
        assert "category" in expense_entry
        assert "amount" in expense_entry

    def test_get_sankey_data(self, test_client, seed_base_transactions):
        """GET /api/analytics/sankey returns sankey diagram data."""
        response = test_client.get("/api/analytics/sankey")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) > 0
        assert len(data["links"]) > 0

    def test_get_overview_empty(self, test_client):
        """GET /api/analytics/overview with no data raises KeyError.

        The service accesses df['date'].max() without guarding against an
        empty DataFrame, so an empty database causes an internal server error.
        """
        with pytest.raises(KeyError):
            test_client.get("/api/analytics/overview")

    def test_get_sankey_empty(self, test_client):
        """GET /api/analytics/sankey with no data returns empty sankey."""
        response = test_client.get("/api/analytics/sankey")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert data["nodes"] == []
        assert data["links"] == []

    def test_get_income_by_source_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source-over-time returns income breakdown."""
        response = test_client.get("/api/analytics/income-by-source-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        entry = data[0]
        assert "month" in entry
        assert "sources" in entry
        assert "total" in entry
        assert isinstance(entry["sources"], dict)
        assert entry["total"] > 0

    def test_get_income_by_source_over_time_date_filter(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source-over-time with date filter narrows results."""
        response = test_client.get(
            "/api/analytics/income-by-source-over-time"
            "?start_date=2024-02-01&end_date=2024-02-28"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["month"] == "2024-02"

    def test_get_income_by_source_over_time_empty(self, test_client):
        """GET /api/analytics/income-by-source-over-time with no data returns empty list."""
        response = test_client.get("/api/analytics/income-by-source-over-time")
        assert response.status_code == 200
        assert response.json() == []
