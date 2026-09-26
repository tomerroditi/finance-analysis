"""Tests for the /api/onboarding API endpoints."""

import pytest


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

    @pytest.mark.parametrize(
        "seed_fixture, flag",
        [
            ("seed_base_transactions", "has_transactions"),
            ("seed_budget_rules", "has_budgets"),
            ("seed_investments", "has_investments"),
        ],
        ids=["transactions", "budgets", "investments"],
    )
    def test_seeded_data_clears_first_run(self, test_client, request, seed_fixture, flag):
        """Seeded transactions, budgets or investments flip their flag and is_first_run."""
        request.getfixturevalue(seed_fixture)
        response = test_client.get("/api/onboarding/status")
        assert response.status_code == 200
        data = response.json()
        assert data[flag] is True
        assert data["is_first_run"] is False
