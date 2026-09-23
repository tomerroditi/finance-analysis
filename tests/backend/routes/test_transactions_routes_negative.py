"""Tests for additional negative/error paths in the /api/transactions endpoints.

Complements ``test_transactions_routes.py`` with validation and edge-case
error scenarios that exercise Pydantic schema validation and missing-field
handling.
"""

import pytest


class TestTransactionValidationErrors:
    """Tests for Pydantic validation errors on transaction endpoints."""

    @pytest.mark.parametrize(
        "overrides",
        [
            None,
            {"amount": ...},
            {"date": ...},
            {"date": "not-a-date"},
            {"service": ...},
        ],
        ids=["empty-body", "no-amount", "no-date", "malformed-date", "no-service"],
    )
    def test_create_transaction_invalid_payload_returns_422(self, test_client, overrides):
        """POST /api/transactions with a missing field or non-ISO date returns 422.

        The ``TransactionCreate`` schema requires ``date`` (ISO
        ``YYYY-MM-DD``), ``description``, ``amount``, ``account_name``, and
        ``service``; ``...`` drops the field from the payload.
        """
        payload = {
            "date": "2024-06-01",
            "description": "Test",
            "amount": -50.0,
            "account_name": "Wallet",
            "service": "cash",
        }
        if overrides is None:
            payload = {}
        else:
            for field, value in overrides.items():
                if value is ...:
                    del payload[field]
                else:
                    payload[field] = value
        response = test_client.post("/api/transactions/", json=payload)
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "http_method, url, body",
        [
            ("put", "/api/transactions/1", {"category": "Food"}),
            (
                "post",
                "/api/transactions/1/split",
                {"splits": [{"amount": -25.0, "category": "Food", "tag": "Groceries"}]},
            ),
            (
                "post",
                "/api/transactions/1/split",
                {"source": "credit_card_transactions", "splits": [{"amount": -25.0}]},
            ),
            (
                "post",
                "/api/transactions/bulk-tag",
                {"source": "credit_card_transactions", "category": "Food", "tag": "Groceries"},
            ),
            (
                "post",
                "/api/transactions/bulk-tag",
                {"transaction_ids": [1, 2], "category": "Food", "tag": "Groceries"},
            ),
            ("delete", "/api/transactions/1", None),
            ("delete", "/api/transactions/1/split", None),
        ],
        ids=[
            "update-no-source",
            "split-no-source",
            "split-incomplete-item",
            "bulk-tag-no-ids",
            "bulk-tag-no-source",
            "delete-no-source-query",
            "revert-split-no-source-query",
        ],
    )
    def test_write_missing_required_input_returns_422(
        self, test_client, http_method, url, body
    ):
        """Transaction writes missing ``source`` or another required input return 422.

        ``TransactionUpdate``, ``SplitRequest`` and ``BulkTagRequest`` require
        ``source``; each ``SplitItem`` requires ``amount``, ``category`` and
        ``tag``; delete and revert-split take ``source`` as a required query
        parameter.
        """
        kwargs = {"json": body} if body is not None else {}
        response = getattr(test_client, http_method)(url, **kwargs)
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

    @pytest.mark.parametrize("literal", ["NaN", "Infinity"])
    def test_create_transaction_rejects_non_finite_amount(self, test_client, literal):
        """Verify a NaN or Infinity amount is rejected with a 422 validation error."""
        response = test_client.post(
            "/api/transactions/",
            content='{"date": "2024-01-01", "description": "x", "amount": '
            + literal
            + ', "account_name": "Wallet", "service": "cash"}',
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


class TestNonIntegerUniqueId:
    """A ``unique_id`` path segment that is not an integer keeps its status codes.

    These routes take ``unique_id`` as a string, so the parse happens in the
    service; the answer (and its message) must not change with that move.
    """

    def test_update_with_non_integer_id_returns_400(self, test_client):
        """PUT /api/transactions/{id} with a non-numeric id is a 400."""
        response = test_client.put(
            "/api/transactions/abc",
            json={"category": "Food", "source": "cash_transactions"},
        )
        assert response.status_code == 400
        assert "invalid literal for int()" in response.json()["detail"]

    def test_delete_with_non_integer_id_returns_404(self, test_client):
        """DELETE /api/transactions/{id} with a non-numeric id is a 404."""
        response = test_client.delete(
            "/api/transactions/abc", params={"source": "cash_transactions"}
        )
        assert response.status_code == 404
        assert "invalid literal for int()" in response.json()["detail"]

    def test_legacy_tag_with_non_integer_id_returns_400(self, test_client):
        """PUT /api/transactions/{id}/tag with a non-numeric id is a 400."""
        response = test_client.put(
            "/api/transactions/abc/tag",
            params={"category": "Food", "tag": "Groceries", "service": "banks"},
        )
        assert response.status_code == 400
        assert "invalid literal for int()" in response.json()["detail"]

    def test_unknown_source_wins_over_non_integer_id(self, test_client):
        """An unknown source is reported before the id is parsed."""
        response = test_client.delete(
            "/api/transactions/abc", params={"source": "not_a_table"}
        )
        assert response.status_code == 400
        assert "not_a_table" in response.json()["detail"]
