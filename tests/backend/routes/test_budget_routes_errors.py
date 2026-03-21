"""Tests for error/negative paths in the /api/budget API endpoints.

Covers validation errors, not-found scenarios, and duplicate detection
for budget rules and project budget endpoints.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestBudgetRuleValidationErrors:
    """Tests for Pydantic validation and business-rule errors on budget endpoints."""

    def test_create_budget_rule_missing_required_fields(self, test_client):
        """POST /api/budget/rules with empty body returns 422.

        The ``BudgetRuleCreate`` schema requires ``name``, ``amount``,
        ``category``, and ``tags``.
        """
        response = test_client.post("/api/budget/rules", json={})
        assert response.status_code == 422

    def test_create_budget_rule_missing_name(self, test_client):
        """POST /api/budget/rules without name returns 422."""
        payload = {
            "amount": 100.0,
            "category": "Food",
            "tags": "Groceries",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422

    def test_create_budget_rule_missing_amount(self, test_client):
        """POST /api/budget/rules without amount returns 422."""
        payload = {
            "name": "Food Budget",
            "category": "Food",
            "tags": "Groceries",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422

    def test_create_budget_rule_missing_category(self, test_client):
        """POST /api/budget/rules without category returns 422."""
        payload = {
            "name": "Food Budget",
            "amount": 100.0,
            "tags": "Groceries",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422

    def test_create_budget_rule_missing_tags(self, test_client):
        """POST /api/budget/rules without tags returns 422."""
        payload = {
            "name": "Food Budget",
            "amount": 100.0,
            "category": "Food",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422

    def test_create_budget_rule_empty_name_returns_400(
        self, test_client, seed_budget_rules
    ):
        """POST /api/budget/rules with empty name string returns 400.

        The service layer validates that the budget rule name is non-empty,
        raising a ValueError that the route maps to a 400 response.
        """
        payload = {
            "name": "",
            "amount": 100.0,
            "category": "Food",
            "tags": "Groceries",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 400

    def test_create_budget_rule_duplicate_name_returns_400(
        self, test_client, seed_budget_rules
    ):
        """POST /api/budget/rules with a duplicate name returns 400.

        The service layer rejects rules with names that already exist
        for the same month/year combination.
        """
        payload = {
            "name": "Food",
            "amount": 999.0,
            "category": "Food",
            "tags": "All Tags",
            "month": 1,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 400


class TestBudgetRuleNotFoundErrors:
    """Tests for not-found scenarios on budget rule endpoints."""

    def test_update_nonexistent_budget_rule(self, test_client):
        """Verify that ValueError propagates when updating a non-existent budget rule.

        The budget repository raises a ValueError when no rule is found
        with the given ID. Since the route has no try/except, the error
        propagates through the test client.
        """
        with pytest.raises(ValueError, match="No rule found"):
            test_client.put(
                "/api/budget/rules/99999",
                json={"amount": 5000.0},
            )

    def test_delete_nonexistent_budget_rule(self, test_client):
        """DELETE /api/budget/rules/99999 for a non-existent rule.

        The repository's delete_rule either silently succeeds (no matching
        row) or raises. We verify the endpoint handles it.
        """
        response = test_client.delete("/api/budget/rules/99999")
        assert response.status_code == 200

    def test_copy_rules_no_previous_month(self, test_client):
        """POST /api/budget/rules/2024/1/copy returns 404 when no previous month.

        December 2023 (the month before January 2024) has no rules seeded,
        so the copy should fail with a 404 response.
        """
        response = test_client.post("/api/budget/rules/2024/1/copy")
        assert response.status_code == 404
        assert "No rules found" in response.json()["detail"]


class TestProjectBudgetErrors:
    """Tests for error paths on project budget endpoints."""

    def test_create_project_missing_required_fields(self, test_client):
        """POST /api/budget/projects with empty body returns 422.

        The ``ProjectCreate`` schema requires ``category`` and ``total_budget``.
        """
        response = test_client.post("/api/budget/projects", json={})
        assert response.status_code == 422

    def test_create_project_missing_category(self, test_client):
        """POST /api/budget/projects without category returns 422."""
        response = test_client.post(
            "/api/budget/projects", json={"total_budget": 5000.0}
        )
        assert response.status_code == 422

    def test_create_project_missing_total_budget(self, test_client):
        """POST /api/budget/projects without total_budget returns 422."""
        response = test_client.post(
            "/api/budget/projects", json={"category": "Housing"}
        )
        assert response.status_code == 422

    def test_update_project_missing_total_budget(self, test_client):
        """PUT /api/budget/projects/{name} without total_budget returns 422.

        The ``ProjectUpdate`` schema requires ``total_budget``.
        """
        response = test_client.put(
            "/api/budget/projects/Wedding", json={}
        )
        assert response.status_code == 422

    def test_get_project_details_nonexistent(self, test_client):
        """Verify that ValueError propagates when fetching a non-existent project.

        The project service raises a ValueError when the project does not
        exist. Since the route has no try/except and the test client has
        ``raise_server_exceptions=True``, the error propagates through.
        """
        with pytest.raises(ValueError, match="not found"):
            test_client.get("/api/budget/projects/NonExistentProject")

    def test_delete_nonexistent_project_succeeds_silently(self, test_client):
        """DELETE /api/budget/projects/NonExistent returns 200.

        The service's ``delete_project`` does not validate existence before
        deleting. When no matching rows exist, the DELETE executes without
        error and returns success.
        """
        response = test_client.delete("/api/budget/projects/NonExistentProject")
        assert response.status_code == 200

    def test_update_nonexistent_project(self, test_client):
        """Verify that ValueError propagates when updating a non-existent project.

        The service raises a ValueError when updating a non-existent project.
        Since the route has no try/except, the error propagates through.
        """
        with pytest.raises(ValueError, match="not found"):
            test_client.put(
                "/api/budget/projects/NonExistentProject",
                json={"total_budget": 60000.0},
            )
