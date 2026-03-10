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

    def test_delete_wallet_returns_400(self, test_client):
        """DELETE /api/cash-balances/Wallet returns 400 because Wallet is protected."""
        # Create Wallet first
        test_client.post("/api/cash-balances/", json={
            "account_name": "Wallet",
            "balance": 500.0,
        })

        response = test_client.delete("/api/cash-balances/Wallet")
        assert response.status_code == 400
        assert "Cannot delete" in response.json()["detail"]

    def test_delete_non_wallet_succeeds(self, test_client):
        """DELETE /api/cash-balances/{name} deletes a non-Wallet account."""
        # Create Wallet (required as migration target) and Savings
        test_client.post("/api/cash-balances/", json={
            "account_name": "Wallet",
            "balance": 0.0,
        })
        test_client.post("/api/cash-balances/", json={
            "account_name": "Savings",
            "balance": 300.0,
        })

        response = test_client.delete("/api/cash-balances/Savings")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify it's gone
        all_balances = test_client.get("/api/cash-balances/").json()
        names = [b["account_name"] for b in all_balances]
        assert "Savings" not in names
        assert "Wallet" in names

    def test_delete_account_migrates_transactions_to_wallet(self, test_client):
        """DELETE /api/cash-balances/{name} migrates transactions to Wallet.

        When an envelope is deleted, its transactions should move to Wallet
        and both cash balances should be recalculated.
        """
        # Create Wallet and Savings envelopes
        test_client.post("/api/cash-balances/", json={
            "account_name": "Wallet",
            "balance": 1000.0,
        })
        test_client.post("/api/cash-balances/", json={
            "account_name": "Savings",
            "balance": 500.0,
        })

        # Create a cash transaction in Savings
        test_client.post("/api/transactions/", json={
            "date": "2024-06-01",
            "description": "Groceries",
            "amount": -50.0,
            "account_name": "Savings",
            "service": "cash",
        })

        # Delete Savings
        response = test_client.delete("/api/cash-balances/Savings")
        assert response.status_code == 200

        # Verify the transaction was migrated to Wallet
        txns = test_client.get("/api/transactions/", params={"service": "cash"}).json()
        savings_txns = [t for t in txns if t["account_name"] == "Savings"]
        wallet_txns = [t for t in txns if t["account_name"] == "Wallet"]
        assert len(savings_txns) == 0
        assert any(t["description"] == "Groceries" for t in wallet_txns)
