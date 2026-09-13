"""Tests for the /api/pending-refunds API endpoints."""


def _mark_bank_expense(test_client, expected_amount: float = 100.0):
    """Mark the first seeded bank expense as awaiting a refund.

    A pending refund only exists over money that was actually spent, so the
    source has to be a real transaction; pick one out of the seeded bank rows
    and return the create response.

    Parameters
    ----------
    test_client : starlette.testclient.TestClient
        Client bound to the seeded test database.
    expected_amount : float, optional
        Amount to expect back; must not exceed the transaction's amount.

    Returns
    -------
    httpx.Response
        The ``POST /api/pending-refunds/`` response.
    """
    txns = test_client.get("/api/transactions/?service=banks").json()
    expense = next(t for t in txns if t["amount"] <= -expected_amount)
    return test_client.post(
        "/api/pending-refunds/",
        json={
            "source_type": "transaction",
            "source_id": expense["unique_id"],
            "source_table": "banks",
            "expected_amount": expected_amount,
        },
    )


class TestPendingRefundsRoutes:
    """Tests for pending refund API endpoints."""

    def _create_pending_refund(self, test_client, seed_base_transactions):
        """Helper to create a pending refund and return the response data."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        tx = txns[0]
        response = test_client.post(
            "/api/pending-refunds/",
            json={
                "source_type": "transaction",
                "source_id": tx["unique_id"],
                "source_table": "credit_cards",
                "expected_amount": abs(tx["amount"]),
            },
        )
        return response, tx

    def test_create_pending_refund(self, test_client, seed_base_transactions):
        """POST /api/pending-refunds/ creates a pending refund."""
        response, tx = self._create_pending_refund(test_client, seed_base_transactions)
        assert response.status_code == 200
        data = response.json()
        assert data["source_type"] == "transaction"
        assert data["source_id"] == tx["unique_id"]
        assert data["status"] == "pending"

    def test_get_all_pending_refunds(self, test_client):
        """GET /api/pending-refunds/ returns empty list when no refunds exist."""
        response = test_client.get("/api/pending-refunds/")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_and_get_pending_refund(self, test_client, seed_base_transactions):
        """Create a pending refund then retrieve it by ID."""
        create_resp, _ = self._create_pending_refund(
            test_client, seed_base_transactions
        )
        pending_id = create_resp.json()["id"]

        response = test_client.get(f"/api/pending-refunds/{pending_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pending_id
        assert "links" in data
        assert "total_refunded" in data

    def test_cancel_pending_refund(self, test_client, seed_base_transactions):
        """DELETE /api/pending-refunds/{id} cancels a pending refund."""
        create_resp, _ = self._create_pending_refund(
            test_client, seed_base_transactions
        )
        pending_id = create_resp.json()["id"]

        response = test_client.delete(f"/api/pending-refunds/{pending_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify it's gone
        get_resp = test_client.get(f"/api/pending-refunds/{pending_id}")
        assert get_resp.status_code == 404

    def test_create_duplicate_pending_refund(
        self, test_client, seed_base_transactions
    ):
        """POST same source twice returns 400 (ValidationException)."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        tx = txns[0]
        payload = {
            "source_type": "transaction",
            "source_id": tx["unique_id"],
            "source_table": "credit_cards",
            "expected_amount": abs(tx["amount"]),
        }
        # First create
        resp1 = test_client.post("/api/pending-refunds/", json=payload)
        assert resp1.status_code == 200

        # Duplicate should fail
        resp2 = test_client.post("/api/pending-refunds/", json=payload)
        assert resp2.status_code == 400

    def test_link_refund(self, test_client, seed_base_transactions):
        """POST /api/pending-refunds/{id}/link links a refund transaction."""
        create_resp, tx = self._create_pending_refund(
            test_client, seed_base_transactions
        )
        pending_id = create_resp.json()["id"]

        # Use a positive (incoming) transaction as the refund transaction
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        txns += test_client.get("/api/transactions/?service=banks").json()
        refund_tx = next(t for t in txns if t["amount"] > 0)

        response = test_client.post(
            f"/api/pending-refunds/{pending_id}/link",
            json={
                "refund_transaction_id": refund_tx["unique_id"],
                "refund_source": refund_tx["source"],
                "amount": min(abs(tx["amount"]), refund_tx["amount"]),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pending_id
        assert data["total_refunded"] > 0


class TestCloseRefundRoute:
    """Tests for POST /pending-refunds/{id}/close endpoint."""

    def test_close_pending_refund(self, test_client, seed_base_transactions):
        """Close a pending refund returns closed status."""
        pending_id = _mark_bank_expense(test_client).json()["id"]
        response = test_client.post(f"/api/pending-refunds/{pending_id}/close")
        assert response.status_code == 200
        assert response.json()["status"] == "closed"
        assert (
            test_client.get(f"/api/pending-refunds/{pending_id}").json()["status"]
            == "closed"
        )

    def test_close_nonexistent_refund(self, test_client):
        """Close nonexistent refund returns 404."""
        response = test_client.post("/api/pending-refunds/9999/close")
        assert response.status_code == 404


class TestUnlinkRefundRoute:
    """Tests for DELETE /pending-refunds/links/{id} endpoint."""

    def test_unlink_refund(self, test_client, seed_base_transactions):
        """Unlink a refund returns updated status."""
        pending_id = _mark_bank_expense(test_client).json()["id"]
        link_resp = test_client.post(f"/api/pending-refunds/{pending_id}/link", json={
            "refund_transaction_id": 99,
            "refund_source": "banks",
            "amount": 50.0,
        })
        assert link_resp.status_code == 200
        details = test_client.get(f"/api/pending-refunds/{pending_id}")
        link_id = details.json()["links"][0]["id"]
        response = test_client.delete(f"/api/pending-refunds/links/{link_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        after = test_client.get(f"/api/pending-refunds/{pending_id}").json()
        assert after["links"] == []
        assert after["total_refunded"] == 0

    def test_unlink_nonexistent_link(self, test_client):
        """Unlink nonexistent link returns 404."""
        response = test_client.delete("/api/pending-refunds/links/9999")
        assert response.status_code == 404


class TestCreatePendingRefundValidation:
    """The create route refuses refunds that no spend backs."""

    def test_missing_source_transaction_returns_400(self, test_client):
        """POST for a source_id that exists in no table returns 400."""
        response = test_client.post(
            "/api/pending-refunds/",
            json={
                "source_type": "transaction",
                "source_id": 99999,
                "source_table": "banks",
                "expected_amount": 100.0,
            },
        )
        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]
        assert test_client.get("/api/pending-refunds/").json() == []

    def test_expected_amount_above_source_returns_400(
        self, test_client, seed_base_transactions
    ):
        """POST expecting more back than was spent returns 400."""
        txns = test_client.get("/api/transactions/?service=banks").json()
        expense = next(t for t in txns if t["amount"] < 0)
        response = test_client.post(
            "/api/pending-refunds/",
            json={
                "source_type": "transaction",
                "source_id": expense["unique_id"],
                "source_table": "banks",
                "expected_amount": abs(expense["amount"]) + 1.0,
            },
        )
        assert response.status_code == 400
        assert "cannot exceed" in response.json()["detail"]


class TestRefundSourcesRoute:
    """Tests for GET /pending-refunds/refund-sources endpoint."""

    def test_refund_sources_empty(self, test_client):
        """Returns an empty list when no refund links exist."""
        response = test_client.get("/api/pending-refunds/refund-sources")
        assert response.status_code == 200
        assert response.json() == []

    def test_refund_sources_reports_allocation(self, test_client, seed_base_transactions):
        """Reports per-transaction allocation totals and availability."""
        txns = test_client.get("/api/transactions/?service=credit_cards").json()
        expense_tx = next(t for t in txns if t["amount"] < 0)
        refund_candidates = [t for t in txns if t["amount"] > 0]
        bank_txns = test_client.get("/api/transactions/?service=banks").json()
        refund_candidates += [t for t in bank_txns if t["amount"] > 0]
        assert refund_candidates, "seed data must contain a positive transaction"
        refund_tx = refund_candidates[0]

        create_resp = test_client.post(
            "/api/pending-refunds/",
            json={
                "source_type": "transaction",
                "source_id": expense_tx["unique_id"],
                "source_table": "credit_cards",
                "expected_amount": min(abs(expense_tx["amount"]), refund_tx["amount"]),
            },
        )
        pending_id = create_resp.json()["id"]

        link_amount = min(abs(expense_tx["amount"]), refund_tx["amount"])
        link_resp = test_client.post(
            f"/api/pending-refunds/{pending_id}/link",
            json={
                "refund_transaction_id": refund_tx["unique_id"],
                "refund_source": refund_tx["source"],
                "amount": link_amount,
            },
        )
        assert link_resp.status_code == 200

        response = test_client.get("/api/pending-refunds/refund-sources")
        assert response.status_code == 200
        sources = response.json()
        assert len(sources) == 1
        src = sources[0]
        assert src["refund_transaction_id"] == refund_tx["unique_id"]
        assert src["total_allocated"] == link_amount
        assert src["transaction_amount"] == refund_tx["amount"]
        assert src["available"] == refund_tx["amount"] - link_amount
        assert len(src["allocations"]) == 1
        assert src["allocations"][0]["pending_refund_id"] == pending_id


class TestRefundNotesRoutes:
    """Tests for the note-editing endpoints."""

    def test_patch_pending_refund_notes(self, test_client, seed_base_transactions):
        """PATCH /pending-refunds/{id} updates the note."""
        pending_id = _mark_bank_expense(test_client).json()["id"]

        resp = test_client.patch(
            f"/api/pending-refunds/{pending_id}", json={"notes": "Store promised refund by Friday"}
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Store promised refund by Friday"

        get_resp = test_client.get(f"/api/pending-refunds/{pending_id}")
        assert get_resp.json()["notes"] == "Store promised refund by Friday"

    def test_patch_pending_refund_notes_not_found(self, test_client):
        """PATCH on a missing pending refund returns 404."""
        resp = test_client.patch("/api/pending-refunds/9999", json={"notes": "x"})
        assert resp.status_code == 404

    def test_put_source_note(self, test_client):
        """PUT /pending-refunds/refund-sources/note upserts and clears."""
        resp = test_client.put("/api/pending-refunds/refund-sources/note", json={
            "refund_source": "banks",
            "refund_transaction_id": 7,
            "note": "Payout for the stolen card claim",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["note"] == "Payout for the stolen card claim"
        assert data["refund_source"] == "bank_transactions"

        resp = test_client.put("/api/pending-refunds/refund-sources/note", json={
            "refund_source": "bank_transactions",
            "refund_transaction_id": 7,
            "note": "",
        })
        assert resp.status_code == 200
        assert resp.json()["note"] is None
