"""Tests for the /api/cash-balances API endpoints."""

import pytest


class TestCashBalancesRoutes:
    """Tests for cash balance API endpoints."""

    def test_get_cash_balances_empty(self, test_client):
        """GET /api/cash-balances/ with no data returns empty list."""
        response = test_client.get("/api/cash-balances/")
        assert response.status_code == 200
        assert response.json() == []

    def test_post_cash_balance_creates_record(self, test_client):
        """POST /api/cash-balances/ creates a balance record."""
        payload = {
            "account_name": "Wallet",
            "balance": 500.0,
        }
        response = test_client.post("/api/cash-balances/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["account_name"] == "Wallet"
        assert data["balance"] == 500.0
        assert data["prior_wealth_amount"] == 500.0  # No transactions yet
        assert "id" in data
        assert "last_manual_update" in data

    def test_post_cash_balance_negative_rejected(self, test_client):
        """POST /api/cash-balances/ rejects negative balance with ValueError.

        The service raises ValueError for negative balance. TestClient re-raises
        this exception in tests, so we catch it with pytest.raises.
        """
        payload = {
            "account_name": "Wallet",
            "balance": -100.0,
        }
        with pytest.raises(ValueError, match="Balance must be >= 0"):
            test_client.post("/api/cash-balances/", json=payload)

    def test_get_cash_balances_after_create(self, test_client):
        """GET /api/cash-balances/ returns created record after POST."""
        # Create a balance
        payload = {
            "account_name": "Savings",
            "balance": 1000.0,
        }
        test_client.post("/api/cash-balances/", json=payload)

        # Get all balances
        response = test_client.get("/api/cash-balances/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        # Find our created balance
        savings_balance = next(
            (b for b in data if b["account_name"] == "Savings"), None
        )
        assert savings_balance is not None
        assert savings_balance["balance"] == 1000.0
