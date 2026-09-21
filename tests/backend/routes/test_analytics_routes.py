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

    def test_a_key_detection_has_not_produced_yet_is_accepted(
        self, test_client, db_session
    ):
        """A verdict is keyed to outlive detection, so it is stored, not 404'd."""
        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": "nothing here", "decision": "confirmed"}]},
        )
        assert response.status_code == 200
        assert response.json()["updated"] == [
            {"normalized": "nothing here", "decision": "confirmed"}
        ]

    def test_a_blank_key_is_400(self, test_client, db_session):
        """A verdict still has to say what it applies to."""
        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": "  ", "decision": "confirmed"}]},
        )
        assert response.status_code == 400

    def test_invalid_decision_is_400(self, test_client, db_session):
        """Only confirmed / dismissed / pending are accepted."""
        norm = self._seed_subscription(test_client, db_session)
        response = test_client.post(
            "/api/analytics/recurring/decisions",
            json={"decisions": [{"normalized": norm, "decision": "maybe"}]},
        )
        assert response.status_code == 400


class TestInsightDismissalRoutes:
    """Tests for the /api/analytics/insights dismissal endpoints."""

    @staticmethod
    def _seed_spike(db_session):
        """Three quiet Food months then a big one, so a spike card exists."""
        import pandas as pd

        from backend.constants.tables import Tables
        from backend.models.transaction import CreditCardTransaction

        def add(description, amount, months_ago):
            date = (
                pd.Timestamp.today().normalize() - pd.DateOffset(months=months_ago)
            ).replace(day=10).strftime("%Y-%m-%d")
            db_session.add(
                CreditCardTransaction(
                    id=f"{description}-{date}",
                    date=date,
                    provider="visa",
                    account_name="card-1",
                    description=description,
                    amount=amount,
                    category="Food",
                    source=Tables.CREDIT_CARD.value,
                )
            )

        for n in range(1, 4):
            add(f"GROCER {n}", -300.0, n)
        add("GROCER NOW", -1500.0, 0)
        db_session.commit()

    def _spike_key(self, test_client, db_session):
        """Seed a spike and return the key of the card it produces."""
        self._seed_spike(db_session)
        cards = test_client.get("/api/analytics/insights").json()
        spike = next(c for c in cards if c["code"] == "categorySpike")
        return spike["key"]

    def test_every_card_carries_a_key(self, test_client, db_session):
        """GET /api/analytics/insights reports the identity each card is dismissed by."""
        self._seed_spike(db_session)
        cards = test_client.get("/api/analytics/insights").json()
        assert cards
        assert all(card["key"] for card in cards)

    def test_dismiss_hides_the_card(self, test_client, db_session):
        """POST /api/analytics/insights/dismiss drops it from the next read."""
        key = self._spike_key(test_client, db_session)

        response = test_client.post(
            "/api/analytics/insights/dismiss", json={"key": key}
        )
        assert response.status_code == 200
        assert response.json() == {"key": key, "dismissed": True}

        cards = test_client.get("/api/analytics/insights").json()
        assert key not in [card["key"] for card in cards]

    def test_restore_brings_it_back(self, test_client, db_session):
        """POST /api/analytics/insights/restore undoes a dismissal."""
        key = self._spike_key(test_client, db_session)
        test_client.post("/api/analytics/insights/dismiss", json={"key": key})

        response = test_client.post(
            "/api/analytics/insights/restore", json={"key": key}
        )
        assert response.status_code == 200
        assert response.json() == {"key": key, "dismissed": False}

        cards = test_client.get("/api/analytics/insights").json()
        assert key in [card["key"] for card in cards]

    def test_dismissing_an_unknown_key_is_harmless(self, test_client):
        """A stale key from an old page is stored without complaint."""
        response = test_client.post(
            "/api/analytics/insights/dismiss", json={"key": "categorySpike:Gone:1999-01"}
        )
        assert response.status_code == 200

    def test_key_is_required(self, test_client):
        """A body with no key is a validation error, not a silent no-op."""
        response = test_client.post("/api/analytics/insights/dismiss", json={})
        assert response.status_code == 422

