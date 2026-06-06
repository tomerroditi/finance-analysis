"""Tests for the /api/budget-month-overrides API endpoints."""

from datetime import date


class TestBudgetMonthOverridesRoutes:
    """Tests for budget month override API endpoints."""

    def _first_cc_transaction(self, test_client):
        """Return the first seeded credit-card transaction dict."""
        return test_client.get("/api/transactions/?service=credit_cards").json()[0]

    def _adjacent_month(self, iso_date: str) -> tuple[int, int]:
        """Return the (year, month) one month after the given ISO date."""
        d = date.fromisoformat(iso_date[:10])
        idx = d.year * 12 + (d.month - 1) + 1
        return idx // 12, idx % 12 + 1

    def test_set_and_list_override(self, test_client, seed_base_transactions):
        """POST creates an override that GET then returns."""
        tx = self._first_cc_transaction(test_client)
        year, month = self._adjacent_month(tx["date"])

        response = test_client.post(
            "/api/budget-month-overrides/",
            json={
                "source_type": "transaction",
                "source_id": tx["unique_id"],
                "source_table": tx["source"],
                "override_year": year,
                "override_month": month,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["override_year"] == year
        assert data["override_month"] == month

        listed = test_client.get("/api/budget-month-overrides/").json()
        assert any(o["id"] == data["id"] for o in listed)

    def test_move_more_than_one_month_returns_400(
        self, test_client, seed_base_transactions
    ):
        """POST moving a transaction two months away returns 400."""
        tx = self._first_cc_transaction(test_client)
        d = date.fromisoformat(tx["date"][:10])
        idx = d.year * 12 + (d.month - 1) + 2  # two months ahead
        response = test_client.post(
            "/api/budget-month-overrides/",
            json={
                "source_type": "transaction",
                "source_id": tx["unique_id"],
                "source_table": tx["source"],
                "override_year": idx // 12,
                "override_month": idx % 12 + 1,
            },
        )
        assert response.status_code == 400

    def test_delete_override(self, test_client, seed_base_transactions):
        """DELETE removes a previously created override."""
        tx = self._first_cc_transaction(test_client)
        year, month = self._adjacent_month(tx["date"])
        created = test_client.post(
            "/api/budget-month-overrides/",
            json={
                "source_type": "transaction",
                "source_id": tx["unique_id"],
                "source_table": tx["source"],
                "override_year": year,
                "override_month": month,
            },
        ).json()

        response = test_client.delete(
            f"/api/budget-month-overrides/{created['id']}"
        )
        assert response.status_code == 200
        assert test_client.get("/api/budget-month-overrides/").json() == []
