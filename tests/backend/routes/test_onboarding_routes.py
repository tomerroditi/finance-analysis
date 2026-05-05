"""Tests for the /api/onboarding API endpoints."""


class TestOnboardingStatusRoute:
    """Tests for GET /api/onboarding/status."""

    def test_status_on_empty_database_marks_first_run(self, test_client):
        """Empty DB should report all flags false and is_first_run true."""
        response = test_client.get("/api/onboarding/status")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "has_credentials": False,
            "has_transactions": False,
            "has_budgets": False,
            "has_investments": False,
            "is_first_run": True,
        }

    def test_status_with_transactions_clears_first_run(
        self, test_client, seed_base_transactions
    ):
        """Seeded transactions should flip has_transactions and is_first_run."""
        response = test_client.get("/api/onboarding/status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_transactions"] is True
        assert data["is_first_run"] is False

    def test_status_with_budgets_clears_first_run(
        self, test_client, seed_budget_rules
    ):
        """Seeded budget rules should flip has_budgets and is_first_run."""
        response = test_client.get("/api/onboarding/status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_budgets"] is True
        assert data["is_first_run"] is False

    def test_status_with_investments_clears_first_run(
        self, test_client, seed_investments
    ):
        """Seeded investments should flip has_investments and is_first_run."""
        response = test_client.get("/api/onboarding/status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_investments"] is True
        assert data["is_first_run"] is False
