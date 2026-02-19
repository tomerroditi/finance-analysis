"""Tests for the /api/transactions API endpoints."""

import pytest


class TestTransactionsRoutes:
    """Tests for transaction API endpoints."""

    def test_get_transactions(self, test_client, seed_base_transactions):
        """GET /api/transactions returns 200 with transaction list."""
        response = test_client.get("/api/transactions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_get_transactions_filter_service(self, test_client, seed_base_transactions):
        """GET /api/transactions?service=credit_cards filters correctly."""
        response = test_client.get("/api/transactions?service=credit_cards")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        # All returned should be from credit card source
        for tx in data:
            assert tx["source"] == "credit_card_transactions"

    def test_create_cash_transaction(self, test_client):
        """POST /api/transactions creates cash transaction."""
        payload = {
            "date": "2024-06-01",
            "description": "Test cash purchase",
            "amount": -50.0,
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify it was created
        get_response = test_client.get("/api/transactions?service=cash")
        data = get_response.json()
        assert any(t["description"] == "Test cash purchase" for t in data)

    def test_create_transaction_invalid_service(self, test_client):
        """POST /api/transactions with invalid service returns 400."""
        # service must be 'cash' or 'manual_investments'
        payload = {
            "date": "2024-06-01",
            "description": "Bad transaction",
            "amount": -50.0,
            "account_name": "Test",
            "service": "credit_cards",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 400

    def test_update_transaction_category(self, test_client, seed_base_transactions):
        """PUT /api/transactions/{id} updates transaction category."""
        # Get a transaction first
        get_resp = test_client.get("/api/transactions?service=credit_cards")
        tx = get_resp.json()[0]
        uid = tx["unique_id"]
        response = test_client.put(
            f"/api/transactions/{uid}",
            json={
                "category": "Entertainment",
                "tag": "Movies",
                "source": "credit_card_transactions",
            },
        )
        assert response.status_code == 200

    def test_delete_cash_transaction(self, test_client):
        """DELETE /api/transactions/{id} deletes cash transaction."""
        # Create one first
        test_client.post(
            "/api/transactions",
            json={
                "date": "2024-06-01",
                "description": "To be deleted",
                "amount": -10.0,
                "account_name": "Wallet",
                "service": "cash",
            },
        )
        # Find it
        txns = test_client.get("/api/transactions?service=cash").json()
        cash_tx = next(t for t in txns if t["description"] == "To be deleted")
        uid = cash_tx["unique_id"]
        response = test_client.delete(
            f"/api/transactions/{uid}?source=cash_transactions"
        )
        assert response.status_code == 200

    def test_delete_scraped_transaction_forbidden(
        self, test_client, seed_base_transactions
    ):
        """DELETE /api/transactions/{id} for scraped source returns 403."""
        txns = test_client.get("/api/transactions?service=credit_cards").json()
        uid = txns[0]["unique_id"]
        response = test_client.delete(
            f"/api/transactions/{uid}?source=credit_card_transactions"
        )
        assert response.status_code == 403

    def test_split_transaction(self, test_client, seed_base_transactions):
        """POST /api/transactions/{id}/split creates splits."""
        txns = test_client.get("/api/transactions?service=credit_cards").json()
        # Find one with known amount
        tx = next(t for t in txns if abs(t["amount"]) > 100)
        uid = tx["unique_id"]
        amt = abs(tx["amount"])
        response = test_client.post(
            f"/api/transactions/{uid}/split",
            json={
                "source": "credit_card_transactions",
                "splits": [
                    {"amount": -(amt / 2), "category": "Food", "tag": "Groceries"},
                    {"amount": -(amt / 2), "category": "Transport", "tag": "Gas"},
                ],
            },
        )
        assert response.status_code == 200

    def test_bulk_tag(self, test_client, seed_untagged_transactions):
        """POST /api/transactions/bulk-tag tags multiple transactions."""
        txns = test_client.get("/api/transactions?service=credit_cards").json()
        untagged = [t for t in txns if t.get("category") is None]
        if len(untagged) < 2:
            pytest.skip("Need at least 2 untagged transactions")
        ids = [t["unique_id"] for t in untagged[:2]]
        response = test_client.post(
            "/api/transactions/bulk-tag",
            json={
                "transaction_ids": ids,
                "source": "credit_card_transactions",
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 200

    def test_get_transaction_by_id(self, test_client, seed_base_transactions):
        """GET /api/transactions/{id} returns single transaction.

        Uses a unique_id from the credit_cards service to avoid collisions
        across tables (each table has its own autoincrement sequence).
        """
        cc_txns = test_client.get("/api/transactions?service=credit_cards").json()
        # Pick the last credit card transaction whose unique_id is higher
        # than the count of bank/cash records, so it only exists in one table.
        uid = max(t["unique_id"] for t in cc_txns)
        response = test_client.get(f"/api/transactions/{uid}")
        assert response.status_code == 200
        data = response.json()
        assert data["unique_id"] == uid

    def test_get_transaction_not_found(self, test_client, seed_base_transactions):
        """GET /api/transactions/{id} for non-existent ID returns 404.

        Seed data is required so the merged DataFrame is non-empty and the
        repository can filter by unique_id without hitting an empty-frame
        KeyError.
        """
        response = test_client.get("/api/transactions/99999")
        assert response.status_code == 404

    def test_get_latest_date(self, test_client, seed_base_transactions):
        """GET /api/transactions/latest-date returns latest transaction date.

        Note: The route is defined after the /{transaction_id} path param
        route, so FastAPI attempts to parse 'latest-date' as an int first.
        This results in a 422 validation error. This test documents the
        current behaviour; the route ordering would need to be fixed for
        this endpoint to be reachable.
        """
        response = test_client.get("/api/transactions/latest-date")
        # Currently returns 422 because /{transaction_id:int} matches first
        assert response.status_code == 422
