"""Tests for error/negative paths in the /api/investments API endpoints.

Covers 404 responses for non-existent investments, Pydantic validation
errors, and exception propagation from the service layer.
"""

import pytest


class TestInvestmentNotFoundErrors:
    """Tests for 404 responses when accessing non-existent investments."""

    def test_get_nonexistent_investment(self, test_client):
        """GET /api/investments/99999 returns 404 for non-existent ID.

        The repository raises ``EntityNotFoundException`` which the global
        exception handler converts to a 404 JSON response.
        """
        response = test_client.get("/api/investments/99999")
        assert response.status_code == 404
        assert "99999" in response.json()["detail"]

    def test_delete_nonexistent_investment(self, test_client):
        """DELETE /api/investments/99999 returns 404 for non-existent ID.

        The repository's ``delete_investment`` calls ``get_by_id`` first,
        which raises ``EntityNotFoundException`` for missing records.
        """
        response = test_client.delete("/api/investments/99999")
        assert response.status_code == 404
        assert "99999" in response.json()["detail"]

    def test_update_nonexistent_investment(self, test_client):
        """PUT /api/investments/99999 returns 404 for non-existent ID.

        The service calls the repository's ``update_investment`` which
        validates the investment exists before applying updates.
        """
        response = test_client.put(
            "/api/investments/99999",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404

    def test_close_nonexistent_investment(self, test_client):
        """POST /api/investments/99999/close returns 404 for non-existent ID."""
        response = test_client.post(
            "/api/investments/99999/close?closed_date=2024-06-01"
        )
        assert response.status_code == 404

    def test_reopen_nonexistent_investment_succeeds_silently(self, test_client):
        """POST /api/investments/99999/reopen returns 200 even for non-existent ID.

        The repository's ``reopen_investment`` does not validate existence
        before issuing the UPDATE statement. A non-matching WHERE clause
        simply updates zero rows without raising an error.
        """
        response = test_client.post("/api/investments/99999/reopen")
        assert response.status_code == 200

    def test_get_analysis_nonexistent_investment(self, test_client):
        """GET /api/investments/99999/analysis returns 404 for non-existent ID."""
        response = test_client.get("/api/investments/99999/analysis")
        assert response.status_code == 404


class TestInvestmentValidationErrors:
    """Tests for Pydantic validation errors on investment endpoints."""

    def test_create_investment_missing_required_fields(self, test_client):
        """POST /api/investments/ with empty body returns 422.

        The ``InvestmentCreate`` schema requires ``category``, ``tag``,
        ``type``, and ``name``.
        """
        response = test_client.post("/api/investments/", json={})
        assert response.status_code == 422

    def test_create_investment_missing_name(self, test_client):
        """POST /api/investments/ without name returns 422."""
        payload = {
            "category": "Investments",
            "tag": "Stocks",
            "type": "stock",
        }
        response = test_client.post("/api/investments/", json=payload)
        assert response.status_code == 422

    def test_create_investment_missing_category(self, test_client):
        """POST /api/investments/ without category returns 422."""
        payload = {
            "tag": "Stocks",
            "type": "stock",
            "name": "Test Fund",
        }
        response = test_client.post("/api/investments/", json=payload)
        assert response.status_code == 422

    def test_create_investment_missing_tag(self, test_client):
        """POST /api/investments/ without tag returns 422."""
        payload = {
            "category": "Investments",
            "type": "stock",
            "name": "Test Fund",
        }
        response = test_client.post("/api/investments/", json=payload)
        assert response.status_code == 422

    def test_create_investment_missing_type(self, test_client):
        """POST /api/investments/ without type returns 422."""
        payload = {
            "category": "Investments",
            "tag": "Stocks",
            "name": "Test Fund",
        }
        response = test_client.post("/api/investments/", json=payload)
        assert response.status_code == 422

    def test_close_investment_missing_closed_date(self, test_client):
        """POST /api/investments/{id}/close without closed_date returns 422.

        The ``closed_date`` query parameter is required.
        """
        response = test_client.post("/api/investments/1/close")
        assert response.status_code == 422


class TestInvestmentBalanceSnapshotErrors:
    """Tests for error paths on balance snapshot endpoints."""

    def test_get_snapshots_nonexistent_investment(self, test_client):
        """GET /api/investments/99999/balances returns empty or 404.

        Depending on implementation, querying snapshots for a non-existent
        investment should either return an empty list or a 404.
        """
        response = test_client.get("/api/investments/99999/balances")
        assert response.status_code in (200, 404)

    def test_create_snapshot_missing_fields(self, test_client):
        """POST /api/investments/1/balances with empty body returns 422.

        The ``BalanceSnapshotCreate`` schema requires ``date`` and ``balance``.
        """
        response = test_client.post(
            "/api/investments/1/balances", json={}
        )
        assert response.status_code == 422

    def test_create_snapshot_missing_date(self, test_client):
        """POST /api/investments/1/balances without date returns 422."""
        response = test_client.post(
            "/api/investments/1/balances",
            json={"balance": 10000.0},
        )
        assert response.status_code == 422

    def test_create_snapshot_missing_balance(self, test_client):
        """POST /api/investments/1/balances without balance returns 422."""
        response = test_client.post(
            "/api/investments/1/balances",
            json={"date": "2024-06-01"},
        )
        assert response.status_code == 422

    def test_delete_snapshot_nonexistent(self, test_client):
        """DELETE /api/investments/1/balances/99999 returns 404.

        The repository raises ``EntityNotFoundException`` for missing
        snapshot IDs.
        """
        response = test_client.delete("/api/investments/1/balances/99999")
        assert response.status_code == 404

    def test_update_snapshot_nonexistent(self, test_client):
        """PUT /api/investments/1/balances/99999 returns 404.

        The repository raises ``EntityNotFoundException`` when no snapshot
        is found with the given ID.
        """
        response = test_client.put(
            "/api/investments/1/balances/99999",
            json={"balance": 15000.0},
        )
        assert response.status_code == 404
