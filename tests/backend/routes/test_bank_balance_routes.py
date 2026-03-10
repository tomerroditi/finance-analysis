"""Tests for the /api/bank-balances API endpoints."""

import pytest


class TestBankBalanceRoutes:
    """Tests for bank balance API endpoints."""

    def test_get_bank_balances_empty(self, test_client):
        """GET /api/bank-balances/ with no data returns empty list."""
        response = test_client.get("/api/bank-balances/")
        assert response.status_code == 200
        assert response.json() == []

    def test_set_bank_balance(self, test_client, monkeypatch):
        """POST /api/bank-balances/ sets a balance."""
        monkeypatch.setattr(
            "backend.services.bank_balance_service.BankBalanceService._validate_scrape_is_today",
            lambda self, provider, account_name: None,
        )
        payload = {
            "provider": "hapoalim",
            "account_name": "Checking",
            "balance": 50000.0,
        }
        response = test_client.post("/api/bank-balances/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "hapoalim"
        assert data["account_name"] == "Checking"
        assert data["balance"] == 50000.0

    def test_set_bank_balance_updates_existing(self, test_client, monkeypatch):
        """POST /api/bank-balances/ with same account updates existing."""
        monkeypatch.setattr(
            "backend.services.bank_balance_service.BankBalanceService._validate_scrape_is_today",
            lambda self, provider, account_name: None,
        )
        payload = {
            "provider": "hapoalim",
            "account_name": "Checking",
            "balance": 45000.0,
        }
        test_client.post("/api/bank-balances/", json=payload)

        # Update with new balance
        payload["balance"] = 48000.0
        response = test_client.post("/api/bank-balances/", json=payload)
        assert response.status_code == 200
        assert response.json()["balance"] == 48000.0

        # Verify only one record exists for this account
        list_resp = test_client.get("/api/bank-balances/")
        balances = list_resp.json()
        matching = [
            b
            for b in balances
            if b["provider"] == "hapoalim" and b["account_name"] == "Checking"
        ]
        assert len(matching) == 1

    def test_get_bank_balances_after_set(self, test_client, monkeypatch):
        """GET /api/bank-balances/ returns records after setting balance."""
        monkeypatch.setattr(
            "backend.services.bank_balance_service.BankBalanceService._validate_scrape_is_today",
            lambda self, provider, account_name: None,
        )
        test_client.post(
            "/api/bank-balances/",
            json={
                "provider": "leumi",
                "account_name": "Savings",
                "balance": 30000.0,
            },
        )
        response = test_client.get("/api/bank-balances/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        providers = [b["provider"] for b in data]
        assert "leumi" in providers
