"""Tests for the /api/analytics API endpoints."""

import pytest


class TestAnalyticsRoutes:
    """Tests for analytics API endpoints."""

    def test_get_overview(self, test_client, seed_base_transactions):
        """GET /api/analytics/overview returns overview with financial data."""
        response = test_client.get("/api/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "total_income" in data
        assert "total_expenses" in data
        assert "net_balance_change" in data
        assert "latest_data_date" in data
        assert data["total_income"] > 0
        assert data["total_expenses"] > 0

    def test_get_net_balance_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/net-balance-over-time returns time series data."""
        response = test_client.get("/api/analytics/net-balance-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Each entry should have month, net_change, and cumulative_balance
        entry = data[0]
        assert "month" in entry
        assert "net_change" in entry
        assert "cumulative_balance" in entry

    def test_get_income_expenses_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-expenses-over-time returns income/expense data."""
        response = test_client.get("/api/analytics/income-expenses-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        entry = data[0]
        assert "month" in entry
        assert "income" in entry
        assert "expenses" in entry

    def test_get_expenses_by_category(self, test_client, seed_base_transactions):
        """GET /api/analytics/by-category returns category breakdown."""
        response = test_client.get("/api/analytics/by-category")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "expenses" in data
        assert "refunds" in data
        assert isinstance(data["expenses"], list)
        # Seed data has expense categories like Food, Transport, Entertainment
        assert len(data["expenses"]) > 0
        expense_entry = data["expenses"][0]
        assert "category" in expense_entry
        assert "amount" in expense_entry

    def test_get_sankey_data(self, test_client, seed_base_transactions):
        """GET /api/analytics/sankey returns sankey diagram data."""
        response = test_client.get("/api/analytics/sankey")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) > 0
        assert len(data["links"]) > 0

    def test_get_overview_empty(self, test_client):
        """GET /api/analytics/overview with no data returns zero-valued totals.

        The service guards against an empty DataFrame (canonical empty
        column schema + NaT-to-None coercion), so a fresh DB returns a
        valid 200 response with zero metrics rather than a 500.
        """
        response = test_client.get("/api/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["latest_data_date"] is None
        assert data["total_income"] == 0
        assert data["total_expenses"] == 0
        assert data["total_investments"] == 0
        assert data["net_balance_change"] == 0

    def test_get_sankey_empty(self, test_client):
        """GET /api/analytics/sankey with no data returns empty sankey."""
        response = test_client.get("/api/analytics/sankey")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert data["nodes"] == []
        assert data["links"] == []

    def test_get_income_by_source_over_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source-over-time returns income breakdown."""
        response = test_client.get("/api/analytics/income-by-source-over-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        entry = data[0]
        assert "month" in entry
        assert "sources" in entry
        assert "total" in entry
        assert isinstance(entry["sources"], dict)
        assert entry["total"] > 0

    def test_get_income_by_source_over_time_empty(self, test_client):
        """GET /api/analytics/income-by-source-over-time with no data returns empty list."""
        response = test_client.get("/api/analytics/income-by-source-over-time")
        assert response.status_code == 200
        assert response.json() == []


class TestIncomeBySourceRoute:
    """Tests for the GET /api/analytics/income-by-source endpoint."""

    def test_get_income_by_source_all_time(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source with no window returns null bounds."""
        response = test_client.get("/api/analytics/income-by-source")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert isinstance(data["sources"], list)
        assert "total" in data
        assert data["start"] is None
        assert data["end"] is None

    def test_get_income_by_source_date_range(self, test_client, seed_base_transactions):
        """GET /api/analytics/income-by-source echoes the requested date window."""
        response = test_client.get(
            "/api/analytics/income-by-source",
            params={"start": "2024-01-01", "end": "2024-01-31"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start"] == "2024-01-01"
        assert data["end"] == "2024-01-31"


class TestRecurringDecisionRoutes:
    """Tests for the confirm / dismiss gate on detected recurring charges."""

    @staticmethod
    def _seed_subscription(test_client, db_session):
        """Seed five monthly charges and return the detected candidate's key."""
        import pandas as pd

        from backend.constants.tables import Tables
        from backend.models.transaction import CreditCardTransaction

        today = pd.Timestamp.today().normalize()
        day = min(10, today.day)
        for n in range(5):
            date = (today - pd.DateOffset(months=n)).replace(day=day).strftime(
                "%Y-%m-%d"
            )
            db_session.add(
                CreditCardTransaction(
                    id=f"netflix-{n}",
                    date=date,
                    provider="visa",
                    account_name="card-1",
                    description="NETFLIX.COM 1234",
                    amount=-45.0,
                    category="Streaming",
                    source=Tables.CREDIT_CARD.value,
                )
            )
        db_session.commit()

        response = test_client.get("/api/analytics/recurring")
        assert response.status_code == 200
        return response.json()["items"][0]["normalized"]

    def test_detected_charge_starts_pending(self, test_client, db_session):
        """GET /api/analytics/recurring reports a new candidate as pending."""
        self._seed_subscription(test_client, db_session)

        data = test_client.get("/api/analytics/recurring").json()
        assert data["items"][0]["confirmation"] == "pending"
        assert data["pending_count"] == 1
        assert data["total_monthly"] == 0.0

    def test_confirming_counts_it_as_recurring(self, test_client, db_session):
        """POST /api/analytics/recurring/decisions confirms a candidate."""
        norm = self._seed_subscription(test_client, db_session)

        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": norm, "decision": "confirmed"}]},
        )
        assert response.status_code == 200
        assert response.json()["updated"] == [
            {"normalized": norm, "decision": "confirmed"}
        ]

        data = test_client.get("/api/analytics/recurring").json()
        assert data["items"][0]["confirmation"] == "confirmed"
        assert data["total_monthly"] == 45.0

    def test_dismissed_charge_needs_the_flag_to_be_listed(
        self, test_client, db_session
    ):
        """A dismissed candidate is hidden unless ``include_dismissed`` asks."""
        norm = self._seed_subscription(test_client, db_session)
        test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": norm, "decision": "dismissed"}]},
        )

        assert test_client.get("/api/analytics/recurring").json()["items"] == []
        listed = test_client.get(
            "/api/analytics/recurring", params={"include_dismissed": True}
        ).json()
        assert listed["items"][0]["confirmation"] == "dismissed"

    def test_unknown_candidate_is_404(self, test_client, db_session):
        """A verdict on something detection never produced is rejected."""
        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": "nothing here", "decision": "confirmed"}]},
        )
        assert response.status_code == 404

    def test_invalid_decision_is_400(self, test_client, db_session):
        """Only confirmed / dismissed / pending are accepted."""
        norm = self._seed_subscription(test_client, db_session)
        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": norm, "decision": "maybe"}]},
        )
        assert response.status_code == 400
