"""Tests for the /api/investments API endpoints."""



class TestInvestmentsRoutes:
    """Tests for investment API endpoints."""

    def test_get_investments(self, test_client, seed_investments):
        """GET /api/investments/ returns investment list."""
        response = test_client.get("/api/investments/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # By default include_closed=False, so only open investments
        assert len(data) >= 1
        # The open one (stock fund) should be present
        names = [inv["name"] for inv in data]
        assert "Migdal S&P 500 Fund" in names

    def test_get_investments_include_closed(self, test_client, seed_investments):
        """GET /api/investments/?include_closed=true returns all investments."""
        response = test_client.get("/api/investments/?include_closed=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = [inv["name"] for inv in data]
        assert "Psagot Government Bond" in names

    def test_create_investment(self, test_client):
        """POST /api/investments/ creates a new investment."""
        payload = {
            "category": "Investments",
            "tag": "Stocks",
            "type": "stock",
            "name": "Test Fund",
        }
        response = test_client.post("/api/investments/", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify it exists
        list_resp = test_client.get("/api/investments/")
        data = list_resp.json()
        assert any(inv["name"] == "Test Fund" for inv in data)

    def test_get_investment_by_id(self, test_client, seed_investments):
        """GET /api/investments/{id} returns single investment."""
        # Get list first to find a valid ID
        list_resp = test_client.get("/api/investments/?include_closed=true")
        investments = list_resp.json()
        inv_id = investments[0]["id"]

        response = test_client.get(f"/api/investments/{inv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == inv_id

    def test_update_investment(self, test_client, seed_investments):
        """PUT /api/investments/{id} updates investment."""
        list_resp = test_client.get("/api/investments/")
        inv_id = list_resp.json()[0]["id"]

        response = test_client.put(
            f"/api/investments/{inv_id}",
            json={"name": "Updated Fund Name"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify update
        get_resp = test_client.get(f"/api/investments/{inv_id}")
        assert get_resp.json()["name"] == "Updated Fund Name"

    def test_close_investment(self, test_client, seed_investments):
        """POST /api/investments/{id}/close closes investment."""
        list_resp = test_client.get("/api/investments/")
        inv_id = list_resp.json()[0]["id"]

        response = test_client.post(
            f"/api/investments/{inv_id}/close?closed_date=2024-06-01"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_reopen_investment(self, test_client, seed_investments):
        """POST /api/investments/{id}/reopen reopens investment."""
        # Get the closed bond fund
        list_resp = test_client.get("/api/investments/?include_closed=true")
        closed = [inv for inv in list_resp.json() if inv["is_closed"]]
        assert len(closed) > 0, "Need a closed investment to test reopen"
        inv_id = closed[0]["id"]

        response = test_client.post(f"/api/investments/{inv_id}/reopen")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_delete_investment(self, test_client, seed_investments):
        """DELETE /api/investments/{id} removes investment."""
        list_resp = test_client.get("/api/investments/?include_closed=true")
        inv_id = list_resp.json()[0]["id"]

        response = test_client.delete(f"/api/investments/{inv_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_get_portfolio_analysis(self, test_client, seed_investments):
        """GET /api/investments/analysis/portfolio returns portfolio metrics."""
        response = test_client.get("/api/investments/analysis/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert "total_value" in data
        assert "total_profit" in data
        assert "portfolio_roi" in data
        assert "allocation" in data
