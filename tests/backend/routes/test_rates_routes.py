"""Tests for the /api/rates API endpoints."""

from unittest.mock import patch


class TestRatesRoutes:
    """Tests for interest rate API endpoints."""

    def test_get_current_rates(self, test_client):
        """GET /api/rates/current returns the latest BoI rate and derived prime."""
        response = test_client.get("/api/rates/current")
        assert response.status_code == 200
        data = response.json()
        assert data["boi_rate"] is not None
        assert abs(data["prime"] - (data["boi_rate"] + 1.5)) < 1e-9
        assert data["as_of"] is not None

    def test_get_history_default_series(self, test_client):
        """GET /api/rates/history returns the seeded BoI series ascending."""
        response = test_client.get("/api/rates/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 20
        dates = [p["date"] for p in data]
        assert dates == sorted(dates)

    def test_get_history_prime_series(self, test_client):
        """GET /api/rates/history?series=prime returns BoI + 1.5."""
        boi = test_client.get("/api/rates/history?series=boi_rate").json()
        prime = test_client.get("/api/rates/history?series=prime").json()
        assert len(boi) == len(prime)
        assert abs(prime[0]["value"] - (boi[0]["value"] + 1.5)) < 1e-9

    def test_get_history_unknown_series_returns_400(self, test_client):
        """GET /api/rates/history with an unknown series returns 400."""
        response = test_client.get("/api/rates/history?series=libor")
        assert response.status_code == 400

    def test_refresh_unavailable_when_offline(self, test_client):
        """POST /api/rates/refresh degrades to status=unavailable on network failure."""
        with patch(
            "backend.services.rates_service.httpx.get",
            side_effect=OSError("offline"),
        ):
            response = test_client.post("/api/rates/refresh")
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
