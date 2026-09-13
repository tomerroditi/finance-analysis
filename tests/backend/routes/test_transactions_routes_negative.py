"""Tests for additional negative/error paths in the /api/transactions endpoints.

Complements ``test_transactions_routes.py`` with validation and edge-case
error scenarios that exercise Pydantic schema validation and missing-field
handling.
"""

import pytest


class TestTransactionValidationErrors:
    """Tests for Pydantic validation errors on transaction endpoints."""

    def test_create_transaction_missing_required_fields(self, test_client):
        """POST /api/transactions with missing required fields returns 422.

        The ``TransactionCreate`` schema requires ``date``, ``description``,
        ``amount``, ``account_name``, and ``service``. Omitting all of them
        triggers FastAPI/Pydantic validation.
        """
        response = test_client.post("/api/transactions/", json={})
        assert response.status_code == 422

    def test_create_transaction_missing_amount(self, test_client):
        """POST /api/transactions without amount field returns 422."""
        payload = {
            "date": "2024-06-01",
            "description": "Test",
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions/", json=payload)
        assert response.status_code == 422

    def test_create_transaction_missing_date(self, test_client):
        """POST /api/transactions without date field returns 422."""
        payload = {
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
            "service": "cash",
        }
        response = test_client.post("/api/transactions/", json=payload)
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
        response = test_client.post("/api/transactions/", json=payload)
        assert response.status_code == 422

    def test_create_transaction_missing_service(self, test_client):
        """POST /api/transactions without service field returns 422."""
        payload = {
            "date": "2024-06-01",
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
        }
        response = test_client.post("/api/transactions/", json=payload)
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

    def test_split_transaction_nonexistent_id_returns_404(self, test_client):
        """POST /api/transactions/{id}/split for a non-existent unique_id returns 404.

        The repository used to silently accept splits for a unique_id that
        didn't exist in the source table, creating orphan rows in
        ``split_transactions`` that no parent could resolve to. The service
        now resolves the parent first and raises
        ``EntityNotFoundException`` — a missing row is a 404, not a bad
        request (the payload itself is well-formed).
        """
        response = test_client.post(
            "/api/transactions/1/split",
            json={
                "source": "credit_card_transactions",
                "splits": [
                    {"amount": -25.0, "category": "Food", "tag": "Groceries"},
                ],
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

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


class TestMissingTransactionWrites:
    """A write against a unique_id that is not in the source table is a 404."""

    def test_update_nonexistent_transaction_returns_404(
        self, test_client, seed_base_transactions
    ):
        """PUT /api/transactions/{id} for a missing row is a 404, not "no_changes".

        The route used to answer 200 ``{"status": "no_changes"}`` because the
        filtered UPDATE simply matched nothing, so a stale row id in the UI
        looked like a successful save.
        """
        response = test_client.put(
            "/api/transactions/99999",
            json={"category": "Food", "source": "cash_transactions"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_nonexistent_transaction_returns_404(self, test_client):
        """DELETE /api/transactions/{id} for a missing row is a 404."""
        response = test_client.delete(
            "/api/transactions/99999?source=cash_transactions"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_rejects_malformed_date(self, test_client):
        """PUT with a date that is not ``YYYY-MM-DD`` is a 400 and writes nothing.

        Dates are stored as strings and compared lexicographically, so one
        unparseable value would sort wrongly forever.
        """
        test_client.post(
            "/api/transactions/",
            json={
                "date": "2024-06-01",
                "description": "Date guard",
                "amount": -10.0,
                "account_name": "Wallet",
                "service": "cash",
            },
        )
        txns = test_client.get("/api/transactions/?service=cash").json()
        uid = next(t["unique_id"] for t in txns if t["description"] == "Date guard")

        response = test_client.put(
            f"/api/transactions/{uid}",
            json={"date": "15/06/2024", "source": "cash_transactions"},
        )
        assert response.status_code == 400
        assert "YYYY-MM-DD" in response.json()["detail"]

        persisted = test_client.get(
            f"/api/transactions/{uid}", params={"source": "cash_transactions"}
        ).json()
        assert persisted["date"] == "2024-06-01"


class TestRevertSplitNotFound:
    """Reverting something that is not a live split is a 404."""

    def test_revert_split_nonexistent_id_returns_404(self, test_client):
        """DELETE /{id}/split for a unique_id in no table returns 404."""
        response = test_client.delete(
            "/api/transactions/99999/split?source=cash_transactions"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_revert_split_on_unsplit_transaction_returns_404(
        self, test_client, seed_base_transactions
    ):
        """DELETE /{id}/split on a normal transaction returns 404 and changes nothing."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        uid = txns[0]["unique_id"]

        response = test_client.delete(
            f"/api/transactions/{uid}/split?source=credit_card_transactions"
        )
        assert response.status_code == 404
        assert "not split" in response.json()["detail"]

        after = test_client.get(
            f"/api/transactions/{uid}", params={"source": "credit_card_transactions"}
        ).json()
        assert after["type"] == "normal"


class TestNaNRejection:
    """Tests for NaN/Infinity rejection in money request fields."""

    def test_create_transaction_rejects_nan_amount(self, test_client):
        """Verify a NaN amount is rejected with a 422 validation error."""
        response = test_client.post(
            "/api/transactions/",
            content='{"date": "2024-01-01", "description": "x", "amount": NaN,'
            ' "account_name": "Wallet", "service": "cash"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_create_transaction_rejects_infinity_amount(self, test_client):
        """Verify an Infinity amount is rejected with a 422 validation error."""
        response = test_client.post(
            "/api/transactions/",
            content='{"date": "2024-01-01", "description": "x", "amount": Infinity,'
            ' "account_name": "Wallet", "service": "cash"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestSplitRequestValidation:
    """Tests for split payload validation (empty splits, amount mismatch)."""

    def test_split_with_empty_splits_is_rejected(self, test_client):
        """POST /api/transactions/{id}/split with an empty splits list returns 422.

        An empty list used to flip the parent to ``split_parent`` with zero
        children, which made the transaction vanish from the merged view and
        from every KPI/budget calculation.
        """
        response = test_client.post(
            "/api/transactions/1/split",
            json={"source": "credit_card_transactions", "splits": []},
        )
        assert response.status_code == 422

    def test_split_amounts_must_sum_to_parent(
        self, test_client, seed_base_transactions
    ):
        """POST /api/transactions/{id}/split rejects splits that don't sum to the parent.

        The frontend modal enforces this invariant (see
        ``.claude/rules/split_transactions.md``); without a server-side check
        the merged view totalled far more than the original transaction.
        """
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        tx = next(t for t in txns if abs(t["amount"]) > 100)
        uid = tx["unique_id"]

        response = test_client.post(
            f"/api/transactions/{uid}/split",
            json={
                "source": "credit_card_transactions",
                "splits": [
                    {"amount": -999999.0, "category": "Food", "tag": "Groceries"},
                    {"amount": -1.0, "category": "Transport", "tag": "Gas"},
                ],
            },
        )
        assert response.status_code == 400
        assert "sum" in response.json()["detail"].lower()

    def test_split_amounts_within_tolerance_are_accepted(
        self, test_client, seed_base_transactions
    ):
        """Rounding drift below the 0.01 tolerance is still accepted."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        tx = next(t for t in txns if abs(t["amount"]) > 100)
        uid = tx["unique_id"]
        amount = tx["amount"]

        response = test_client.post(
            f"/api/transactions/{uid}/split",
            json={
                "source": "credit_card_transactions",
                "splits": [
                    {
                        "amount": round(amount / 2, 2) + 0.004,
                        "category": "Food",
                        "tag": "Groceries",
                    },
                    {
                        "amount": amount - round(amount / 2, 2) - 0.004,
                        "category": "Transport",
                        "tag": "Gas",
                    },
                ],
            },
        )
        assert response.status_code == 200

        after = test_client.get("/api/transactions/?service=credit_cards").json()
        children = [t for t in after if t.get("split_id") is not None]
        assert len(children) == 2
        assert sum(c["amount"] for c in children) == pytest.approx(amount)
        assert not any(t["unique_id"] == uid for t in after)


class TestUnknownSourceHandling:
    """Tests that an unrecognised ``source`` yields 400, never 500."""

    def test_update_transaction_unknown_source(self, test_client):
        """PUT /api/transactions/{id} with an unknown source returns 400."""
        response = test_client.put(
            "/api/transactions/1",
            json={"category": "Food", "source": "not_a_table"},
        )
        assert response.status_code == 400
        assert "not_a_table" in response.json()["detail"]

    def test_split_transaction_unknown_source(self, test_client):
        """POST /api/transactions/{id}/split with an unknown source returns 400."""
        response = test_client.post(
            "/api/transactions/1/split",
            json={
                "source": "not_a_table",
                "splits": [
                    {"amount": -25.0, "category": "Food", "tag": "Groceries"},
                ],
            },
        )
        assert response.status_code == 400
        assert "not_a_table" in response.json()["detail"]

    def test_revert_split_unknown_source(self, test_client):
        """DELETE /api/transactions/{id}/split with an unknown source returns 400."""
        response = test_client.delete(
            "/api/transactions/1/split?source=not_a_table"
        )
        assert response.status_code == 400
        assert "not_a_table" in response.json()["detail"]


class TestDeleteUnknownSource:
    """An unknown source is a bad request, not a permission failure."""

    def test_delete_with_unknown_source_returns_400(self, test_client):
        """DELETE with a nonexistent source table returns 400, not 403."""
        response = test_client.delete(
            "/api/transactions/1", params={"source": "not_a_table"}
        )
        assert response.status_code == 400
