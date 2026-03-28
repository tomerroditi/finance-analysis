"""Tests for the /api/liabilities API endpoints."""

import pytest


class TestLiabilitiesRoutes:
    """Tests for liability API endpoints."""

    def test_get_liabilities(self, test_client, seed_liabilities):
        """GET /api/liabilities/ returns active liabilities list excluding paid-off ones."""
        response = test_client.get("/api/liabilities/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [item["name"] for item in data]
        assert "Car Loan" in names

    def test_get_liabilities_include_paid_off(self, test_client, seed_liabilities):
        """GET /api/liabilities/?include_paid_off=true returns all liabilities including paid-off."""
        response = test_client.get("/api/liabilities/?include_paid_off=true")
        assert response.status_code == 200
        data = response.json()
        names = [item["name"] for item in data]
        assert "Student Loan" in names

    def test_create_liability(self, test_client):
        """POST /api/liabilities/ creates a new liability and it appears in the list."""
        payload = {
            "name": "Personal Loan",
            "tag": "Personal Loan",
            "principal_amount": 10000.0,
            "interest_rate": 5.0,
            "term_months": 24,
            "start_date": "2024-01-01",
            "lender": "Test Bank",
        }
        response = test_client.post("/api/liabilities/", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        list_resp = test_client.get("/api/liabilities/")
        names = [item["name"] for item in list_resp.json()]
        assert "Personal Loan" in names

    def test_get_liability_by_id(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id} returns single liability with monthly_payment field."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liability_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == liability_id
        assert "monthly_payment" in data

    def test_update_liability(self, test_client, seed_liabilities):
        """PUT /api/liabilities/{id} updates the liability name."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        response = test_client.put(
            f"/api/liabilities/{liability_id}",
            json={"name": "Updated Car Loan"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        get_resp = test_client.get(f"/api/liabilities/{liability_id}")
        assert get_resp.json()["name"] == "Updated Car Loan"

    def test_pay_off_and_reopen(self, test_client, seed_liabilities):
        """POST pay-off removes from default list; reopen restores it."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        pay_off_resp = test_client.post(
            f"/api/liabilities/{liability_id}/pay-off",
            json={"paid_off_date": "2025-06-01"},
        )
        assert pay_off_resp.status_code == 200
        assert pay_off_resp.json()["status"] == "success"

        list_after = test_client.get("/api/liabilities/")
        ids_after = [item["id"] for item in list_after.json()]
        assert liability_id not in ids_after

        reopen_resp = test_client.post(f"/api/liabilities/{liability_id}/reopen")
        assert reopen_resp.status_code == 200
        assert reopen_resp.json()["status"] == "success"

        list_reopened = test_client.get("/api/liabilities/")
        ids_reopened = [item["id"] for item in list_reopened.json()]
        assert liability_id in ids_reopened

    def test_delete_liability(self, test_client, seed_liabilities):
        """DELETE /api/liabilities/{id} removes the liability, GET returns 404."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        delete_resp = test_client.delete(f"/api/liabilities/{liability_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "success"

        get_resp = test_client.get(f"/api/liabilities/{liability_id}")
        assert get_resp.status_code == 404

    def test_get_analysis(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id}/analysis returns schedule, transactions, actual_vs_expected, summary."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liability_id}/analysis")
        assert response.status_code == 200
        data = response.json()
        assert "schedule" in data
        assert "transactions" in data
        assert "actual_vs_expected" in data
        assert "summary" in data

    def test_get_transactions(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id}/transactions returns a list of transactions."""
        list_resp = test_client.get("/api/liabilities/")
        liability_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liability_id}/transactions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
