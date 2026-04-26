"""Tests for the /api/transactions API endpoints."""

import pytest
from unittest.mock import patch, MagicMock


class TestTransactionsRoutes:
    """Tests for transaction API endpoints."""

    def test_get_transactions(self, test_client, seed_base_transactions):
        """GET /api/transactions returns 200 with transaction list."""
        response = test_client.get("/api/transactions/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_get_transactions_filter_service(self, test_client, seed_base_transactions):
        """GET /api/transactions?service=credit_cards filters correctly."""
        response = test_client.get("/api/transactions/?service=credit_cards")
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
        response = test_client.post("/api/transactions/", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify it was created
        get_response = test_client.get("/api/transactions/?service=cash")
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
        response = test_client.post("/api/transactions/", json=payload)
        assert response.status_code == 400

    def test_update_transaction_category(self, test_client, seed_base_transactions):
        """PUT /api/transactions/{id} updates transaction category."""
        # Get a transaction first
        get_resp = test_client.get("/api/transactions/?service=credit_cards")
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

    def test_update_cash_transaction_account_name(self, test_client):
        """PUT /api/transactions/{id} updates cash transaction account_name."""
        # Create a cash transaction first
        create_resp = test_client.post(
            "/api/transactions/",
            json={
                "date": "2024-06-01",
                "description": "Test account update",
                "amount": -30.0,
                "account_name": "Wallet A",
                "service": "cash",
            },
        )
        assert create_resp.status_code == 200

        # Get the transaction to find its ID
        get_resp = test_client.get("/api/transactions/?service=cash")
        txs = get_resp.json()
        tx = next((t for t in txs if t.get("description") == "Test account update"), None)
        assert tx is not None
        uid = tx["unique_id"]

        # Update the account_name
        response = test_client.put(
            f"/api/transactions/{uid}",
            json={
                "account_name": "Wallet B",
                "source": "cash_transactions",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify the update was applied
        get_resp2 = test_client.get(f"/api/transactions/{uid}")
        assert get_resp2.status_code == 200
        updated_tx = get_resp2.json()
        assert updated_tx["account_name"] == "Wallet B"

    def test_delete_cash_transaction(self, test_client):
        """DELETE /api/transactions/{id} deletes cash transaction."""
        # Create one first
        test_client.post(
            "/api/transactions/",
            json={
                "date": "2024-06-01",
                "description": "To be deleted",
                "amount": -10.0,
                "account_name": "Wallet",
                "service": "cash",
            },
        )
        # Find it
        txns = test_client.get("/api/transactions/?service=cash").json()
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
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        uid = txns[0]["unique_id"]
        response = test_client.delete(
            f"/api/transactions/{uid}?source=credit_card_transactions"
        )
        assert response.status_code == 403

    def test_split_transaction(self, test_client, seed_base_transactions):
        """POST /api/transactions/{id}/split creates splits."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
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
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
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
        cc_txns = test_client.get("/api/transactions/?service=credit_cards").json()
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


class TestTransactionsRoutesErrors:
    """Tests for error handling in transaction route endpoints."""

    # -- POST / error paths --

    def test_create_transaction_value_error(self, test_client):
        """Verify 400 when create_transaction raises ValueError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.create_transaction.side_effect = ValueError("Invalid service")
            response = test_client.post(
                "/api/transactions/",
                json={
                    "date": "2024-01-01",
                    "description": "Test",
                    "amount": -50.0,
                    "account_name": "Cash",
                    "service": "invalid",
                },
            )
            assert response.status_code == 400
            assert "Invalid service" in response.json()["detail"]

    def test_create_transaction_runtime_error(self, test_client):
        """Verify 500 when create_transaction raises RuntimeError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.create_transaction.side_effect = RuntimeError("DB write failed")
            response = test_client.post(
                "/api/transactions/",
                json={
                    "date": "2024-01-01",
                    "description": "Test",
                    "amount": -50.0,
                    "account_name": "Cash",
                    "service": "cash",
                },
            )
            assert response.status_code == 500
            assert "DB write failed" in response.json()["detail"]

    # -- PUT /{unique_id} error path --

    def test_update_transaction_internal_error(self, test_client):
        """Verify unexpected exceptions propagate out of the route (no try/except)."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_transaction.side_effect = RuntimeError("Update crashed")
            with pytest.raises(RuntimeError, match="Update crashed"):
                test_client.put(
                    "/api/transactions/1",
                    json={
                        "category": "Food",
                        "tag": "Groceries",
                        "source": "credit_card_transactions",
                    },
                )

    def test_update_transaction_value_error(self, test_client):
        """Verify 400 when update_transaction raises ValueError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_transaction.side_effect = ValueError("Bad source")
            response = test_client.put(
                "/api/transactions/1",
                json={
                    "category": "Food",
                    "tag": "Groceries",
                    "source": "credit_card_transactions",
                },
            )
            assert response.status_code == 400
            assert "Bad source" in response.json()["detail"]

    # -- DELETE /{unique_id} error paths --

    def test_delete_transaction_permission_error(self, test_client):
        """Verify 403 when delete_transaction raises PermissionError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.delete_transaction.side_effect = PermissionError(
                "Cannot delete scraped transactions"
            )
            response = test_client.delete(
                "/api/transactions/1?source=credit_card_transactions"
            )
            assert response.status_code == 403
            assert "Cannot delete" in response.json()["detail"]

    def test_delete_transaction_value_error(self, test_client):
        """Verify 404 when delete_transaction raises ValueError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.delete_transaction.side_effect = ValueError(
                "Transaction not found"
            )
            response = test_client.delete(
                "/api/transactions/99999?source=cash_transactions"
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    # -- POST /{unique_id}/split error path --

    def test_split_transaction_value_error(self, test_client):
        """Verify 400 when split_transaction raises ValueError (e.g. failed commit)."""
        with patch(
            "backend.routes.transactions.TransactionsService"
        ) as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.split_transaction.side_effect = ValueError(
                "Failed to split transaction"
            )
            response = test_client.post(
                "/api/transactions/1/split",
                json={
                    "source": "credit_card_transactions",
                    "splits": [
                        {"amount": -25.0, "category": "Food", "tag": "Groceries"},
                        {"amount": -25.0, "category": "Transport", "tag": "Gas"},
                    ],
                },
            )
            assert response.status_code == 400
            assert "Failed to split" in response.json()["detail"]

    # -- DELETE /{unique_id}/split error path --

    def test_revert_split_value_error(self, test_client):
        """Verify 400 when revert_split raises ValueError (e.g. failed commit)."""
        with patch(
            "backend.routes.transactions.TransactionsService"
        ) as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.revert_split.side_effect = ValueError("Failed to revert split")
            response = test_client.delete(
                "/api/transactions/1/split?source=credit_card_transactions"
            )
            assert response.status_code == 400
            assert "Failed to revert" in response.json()["detail"]

    # -- POST /bulk-tag error path --

    def test_bulk_tag_value_error(self, test_client):
        """Verify 400 when bulk_tag_transactions raises ValueError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.bulk_tag_transactions.side_effect = ValueError(
                "Bad input"
            )
            response = test_client.post(
                "/api/transactions/bulk-tag",
                json={
                    "transaction_ids": [1, 2],
                    "source": "credit_card_transactions",
                    "category": "Food",
                    "tag": "Groceries",
                },
            )
            assert response.status_code == 400
            assert "Bad input" in response.json()["detail"]


class TestTransactionsRoutesAdditional:
    """Tests for additional and legacy transaction route endpoints."""

    # -- PUT /{transaction_id}/tag legacy endpoint --

    def test_update_transaction_tag_success(self, test_client):
        """Verify legacy PUT /{id}/tag endpoint returns success."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_tagging_by_id.return_value = None
            response = test_client.put(
                "/api/transactions/1/tag?category=Food&tag=Groceries&service=credit_cards"
            )
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            mock_svc.update_tagging_by_id.assert_called_once_with(
                "credit_cards", "1", "Food", "Groceries"
            )

    def test_update_transaction_tag_value_error(self, test_client):
        """Verify 400 when legacy tag update raises ValueError."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_tagging_by_id.side_effect = ValueError(
                "Bad input"
            )
            response = test_client.put(
                "/api/transactions/1/tag?category=Food&tag=Groceries&service=credit_cards"
            )
            assert response.status_code == 400
            assert "Bad input" in response.json()["detail"]

    # -- GET /{transaction_id} error path (already tested in main class, but
    #    we test the mock path for completeness) --

    def test_get_transaction_by_id_not_found_via_mock(self, test_client):
        """Verify 404 when repository raises ValueError for missing transaction."""
        with patch(
            "backend.routes.transactions.TransactionsRepository"
        ) as mock_cls:
            mock_repo = MagicMock()
            mock_cls.return_value = mock_repo
            mock_repo.get_transaction_by_id.side_effect = ValueError(
                "Transaction 99999 not found"
            )
            response = test_client.get("/api/transactions/99999")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    # -- POST /{unique_id}/split returns false --

    def test_split_transaction_repo_returns_false(self, test_client):
        """Verify 400 when underlying repo returns False (service raises ValueError)."""
        with patch(
            "backend.services.transactions_service.TransactionsRepository"
        ) as mock_cls:
            mock_repo = MagicMock()
            mock_cls.return_value = mock_repo
            mock_repo.split_transaction.return_value = False
            response = test_client.post(
                "/api/transactions/1/split",
                json={
                    "source": "credit_card_transactions",
                    "splits": [
                        {"amount": -25.0, "category": "Food", "tag": "Groceries"},
                        {"amount": -25.0, "category": "Transport", "tag": "Gas"},
                    ],
                },
            )
            assert response.status_code == 400
            assert "Failed to split" in response.json()["detail"]

    # -- DELETE /{unique_id}/split returns false --

    def test_revert_split_repo_returns_false(self, test_client):
        """Verify 400 when underlying repo returns False (service raises ValueError)."""
        with patch(
            "backend.services.transactions_service.TransactionsRepository"
        ) as mock_cls:
            mock_repo = MagicMock()
            mock_cls.return_value = mock_repo
            mock_repo.revert_split.return_value = False
            response = test_client.delete(
                "/api/transactions/1/split?source=credit_card_transactions"
            )
            assert response.status_code == 400
            assert "Failed to revert" in response.json()["detail"]

    # -- GET / internal error --

    def test_get_transactions_internal_error(self, test_client):
        """Verify unexpected exceptions propagate out of the GET route (no try/except)."""
        with patch(
            "backend.routes.transactions.TransactionsRepository"
        ) as mock_cls:
            mock_repo = MagicMock()
            mock_cls.return_value = mock_repo
            mock_repo.get_table.side_effect = RuntimeError("Read failed")
            with pytest.raises(RuntimeError, match="Read failed"):
                test_client.get("/api/transactions/")
