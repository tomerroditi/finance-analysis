"""Tests for additional negative/error paths in the /api/transactions endpoints.

Complements ``test_transactions_routes.py`` with validation and edge-case
error scenarios that exercise Pydantic schema validation and missing-field
handling.
"""

from unittest.mock import patch, MagicMock


class TestTransactionValidationErrors:
    """Tests for Pydantic validation errors on transaction endpoints."""

    def test_create_transaction_missing_required_fields(self, test_client):
        """POST /api/transactions with missing required fields returns 422.

        The ``TransactionCreate`` schema requires ``date``, ``description``,
        ``amount``, ``account_name``, and ``service``. Omitting all of them
        triggers FastAPI/Pydantic validation.
        """
        response = test_client.post("/api/transactions", json={})
        assert response.status_code == 422

    def test_create_transaction_missing_amount(self, test_client):
        """POST /api/transactions without amount field returns 422."""
        payload = {
            "date": "2024-06-01",
            "description": "Test",
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 422

    def test_create_transaction_missing_date(self, test_client):
        """POST /api/transactions without date field returns 422."""
        payload = {
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 422

    def test_create_transaction_invalid_date_format(self, test_client):
        """POST /api/transactions with malformed date returns 422.

        Pydantic expects an ISO date string (``YYYY-MM-DD``). An invalid
        format should be caught during request parsing.
        """
        payload = {
            "date": "not-a-date",
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 422

    def test_create_transaction_missing_service(self, test_client):
        """POST /api/transactions without service field returns 422."""
        payload = {
            "date": "2024-06-01",
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
        }
        response = test_client.post("/api/transactions", json=payload)
        assert response.status_code == 422

    def test_update_transaction_missing_source(self, test_client):
        """PUT /api/transactions/{id} without source returns 422.

        The ``TransactionUpdate`` schema requires the ``source`` field.
        """
        response = test_client.put(
            "/api/transactions/1",
            json={"category": "Food"},
        )
        assert response.status_code == 422

    def test_split_transaction_empty_splits_succeeds(self, test_client):
        """POST /api/transactions/{id}/split with empty splits list returns 200.

        An empty splits array passes Pydantic validation and the repository
        layer processes it without error, returning success. This documents
        the current behavior where no validation rejects empty splits.
        """
        response = test_client.post(
            "/api/transactions/1/split",
            json={"source": "credit_card_transactions", "splits": []},
        )
        assert response.status_code == 200

    def test_split_transaction_missing_source(self, test_client):
        """POST /api/transactions/{id}/split without source returns 422."""
        response = test_client.post(
            "/api/transactions/1/split",
            json={
                "splits": [
                    {"amount": -25.0, "category": "Food", "tag": "Groceries"},
                ],
            },
        )
        assert response.status_code == 422

    def test_split_transaction_invalid_split_item(self, test_client):
        """POST /api/transactions/{id}/split with incomplete split item returns 422.

        Each ``SplitItem`` requires ``amount``, ``category``, and ``tag``.
        """
        response = test_client.post(
            "/api/transactions/1/split",
            json={
                "source": "credit_card_transactions",
                "splits": [{"amount": -25.0}],
            },
        )
        assert response.status_code == 422

    def test_bulk_tag_missing_transaction_ids(self, test_client):
        """POST /api/transactions/bulk-tag without transaction_ids returns 422."""
        response = test_client.post(
            "/api/transactions/bulk-tag",
            json={
                "source": "credit_card_transactions",
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 422

    def test_bulk_tag_missing_source(self, test_client):
        """POST /api/transactions/bulk-tag without source returns 422."""
        response = test_client.post(
            "/api/transactions/bulk-tag",
            json={
                "transaction_ids": [1, 2],
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 422

    def test_delete_transaction_missing_source_query(self, test_client):
        """DELETE /api/transactions/{id} without source query param returns 422.

        The ``source`` query parameter is required for deletion.
        """
        response = test_client.delete("/api/transactions/1")
        assert response.status_code == 422

    def test_revert_split_missing_source_query(self, test_client):
        """DELETE /api/transactions/{id}/split without source returns 422."""
        response = test_client.delete("/api/transactions/1/split")
        assert response.status_code == 422


class TestTransactionNotFoundErrors:
    """Tests for 404 responses when accessing non-existent transactions."""

    def test_get_nonexistent_transaction_empty_db(self, test_client):
        """GET /api/transactions/99999 on empty DB returns 404.

        When the database is empty, the repository should raise a ValueError
        that the route maps to a 404 response.
        """
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

    def test_delete_nonexistent_transaction(self, test_client):
        """DELETE /api/transactions/99999 for missing transaction returns 404."""
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.delete_transaction.side_effect = ValueError(
                "Transaction 99999 not found"
            )
            response = test_client.delete(
                "/api/transactions/99999?source=cash_transactions"
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_update_nonexistent_transaction(self, test_client):
        """PUT /api/transactions/99999 for missing transaction returns 500.

        The update route catches all exceptions as 500 since it uses a
        generic ``except Exception`` handler.
        """
        with patch("backend.routes.transactions.TransactionsService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_transaction.side_effect = ValueError(
                "Transaction not found"
            )
            response = test_client.put(
                "/api/transactions/99999",
                json={
                    "category": "Food",
                    "source": "cash_transactions",
                },
            )
            assert response.status_code == 500
            assert "not found" in response.json()["detail"]
