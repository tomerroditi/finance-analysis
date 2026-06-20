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
        assert "total_income" in data
        assert "total_expenses" in data
        assert "net_balance_change" in data
        assert "latest_data_date" in data
        assert data["total_income"] > 0
        assert data["total_expenses"] > 0

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
        """GET /api/analytics/overview with no data returns zero-valued totals.

        The service guards against an empty DataFrame (canonical empty
        column schema + NaT-to-None coercion), so a fresh DB returns a
        valid 200 response with zero metrics rather than a 500.
        """
        response = test_client.get("/api/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["latest_data_date"] is None
        assert data["total_income"] == 0
        assert data["total_expenses"] == 0
        assert data["total_investments"] == 0
        assert data["net_balance_change"] == 0

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

    def test_get_income_by_source_over_time_empty(self, test_client):
        """GET /api/analytics/income-by-source-over-time with no data returns empty list."""
        response = test_client.get("/api/analytics/income-by-source-over-time")
        assert response.status_code == 200
        assert response.json() == []


class TestIncomeBySourceRoute:
    """Tests for the GET /api/analytics/income-by-source endpoint."""

    def test_get_income_by_source_all_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source with no window returns null bounds."""
        response = test_client.get("/api/analytics/income-by-source")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert isinstance(data["sources"], list)
        assert "total" in data
        assert data["start"] is None
        assert data["end"] is None

    def test_get_income_by_source_date_range(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source echoes the requested date window."""
        response = test_client.get(
            "/api/analytics/income-by-source",
            params={"start": "2024-01-01", "end": "2024-01-31"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start"] == "2024-01-01"
        assert data["end"] == "2024-01-31"
