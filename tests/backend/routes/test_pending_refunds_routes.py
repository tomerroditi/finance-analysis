"""Tests for the /api/pending-refunds API endpoints."""



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

    def test_close_pending_refund(self, test_client):
        """Close a pending refund returns closed status."""
        create_resp = test_client.post("/api/pending-refunds/", json={
            "source_type": "transaction",
            "source_id": 1,
            "source_table": "banks",
            "expected_amount": 100.0,
        })
        pending_id = create_resp.json()["id"]
        response = test_client.post(f"/api/pending-refunds/{pending_id}/close")
        assert response.status_code == 200
        assert response.json()["status"] == "closed"

    def test_close_nonexistent_refund(self, test_client):
        """Close nonexistent refund returns 404."""
        response = test_client.post("/api/pending-refunds/9999/close")
        assert response.status_code == 404


class TestUnlinkRefundRoute:
    """Tests for DELETE /pending-refunds/links/{id} endpoint."""

    def test_unlink_refund(self, test_client):
        """Unlink a refund returns updated status."""
        create_resp = test_client.post("/api/pending-refunds/", json={
            "source_type": "transaction",
            "source_id": 1,
            "source_table": "banks",
            "expected_amount": 100.0,
        })
        pending_id = create_resp.json()["id"]
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

    def test_unlink_nonexistent_link(self, test_client):
        """Unlink nonexistent link returns 404."""
        response = test_client.delete("/api/pending-refunds/links/9999")
        assert response.status_code == 404


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
