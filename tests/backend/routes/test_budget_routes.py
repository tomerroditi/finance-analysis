"""Tests for the /api/budget API endpoints."""

import pytest


SAMPLE_CATEGORIES = {
    "Food": ["Groceries", "Restaurants"],
    "Transport": ["Gas", "Public Transport"],
    "Entertainment": ["Cinema", "Streaming"],
    "Salary": [],
    "Other Income": [],
    "Investments": [],
    "Ignore": [],
    "Liabilities": [],
    "Credit Cards": [],
    "Housing": ["Rent", "Utilities"],
    "Wedding": ["Venue", "Catering"],
    "Renovation": ["Materials", "Labor"],
}


class TestBudgetRoutes:
    """Tests for budget API endpoints."""

    def test_get_budget_rules(self, test_client, seed_budget_rules):
        """GET /api/budget/rules returns all rules."""
        response = test_client.get("/api/budget/rules")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4

    def test_get_budget_rules_by_month(self, test_client, seed_budget_rules):
        """GET /api/budget/rules/2024/1 returns monthly rules."""
        response = test_client.get("/api/budget/rules/2024/1")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4
        names = {r["name"] for r in data}
        assert "Total Budget" in names
        assert "Food" in names

    def test_get_budget_rules_by_month_empty(self, test_client, seed_budget_rules):
        """GET /api/budget/rules/2025/6 returns empty list for month without rules."""
        response = test_client.get("/api/budget/rules/2025/6")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_create_budget_rule(self, test_client):
        """POST /api/budget/rules creates a rule for a fresh month."""
        # Create a Total Budget rule first (required for validation)
        total_payload = {
            "name": "Total Budget",
            "amount": 5000.0,
            "category": "Total Budget",
            "tags": "All Tags",
            "month": 6,
            "year": 2024,
        }
        resp = test_client.post("/api/budget/rules", json=total_payload)
        assert resp.status_code == 200

        # Now create a category rule under that total budget
        payload = {
            "name": "Hobbies",
            "amount": 200.0,
            "category": "Entertainment",
            "tags": "Cinema",
            "month": 6,
            "year": 2024,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify the rule was created
        rules_response = test_client.get("/api/budget/rules/2024/6")
        data = rules_response.json()
        assert any(r["name"] == "Hobbies" for r in data)

    def test_create_budget_rule_invalid(self, test_client, seed_budget_rules):
        """POST /api/budget/rules with empty name returns 400."""
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

    def test_update_budget_rule(self, test_client, seed_budget_rules):
        """PUT /api/budget/rules/{id} updates a rule."""
        # Get the rules to find an ID
        rules_response = test_client.get("/api/budget/rules/2024/1")
        rules = rules_response.json()
        food_rule = next(r for r in rules if r["name"] == "Food")
        rule_id = food_rule["id"]

        payload = {"amount": 2500.0}
        response = test_client.put(f"/api/budget/rules/{rule_id}", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify the update
        updated_rules = test_client.get("/api/budget/rules/2024/1").json()
        updated_food = next(r for r in updated_rules if r["name"] == "Food")
        assert updated_food["amount"] == 2500.0

    def test_delete_budget_rule(self, test_client, seed_budget_rules):
        """DELETE /api/budget/rules/{id} deletes a rule."""
        rules_response = test_client.get("/api/budget/rules/2024/1")
        rules = rules_response.json()
        entertainment_rule = next(r for r in rules if r["name"] == "Entertainment")
        rule_id = entertainment_rule["id"]

        response = test_client.delete(f"/api/budget/rules/{rule_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify deletion
        updated_rules = test_client.get("/api/budget/rules/2024/1").json()
        assert not any(r["name"] == "Entertainment" for r in updated_rules)

    def test_copy_previous_month_rules(self, test_client, seed_budget_rules):
        """POST /api/budget/rules/2024/2/copy copies rules from January to February."""
        response = test_client.post("/api/budget/rules/2024/2/copy")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify the copied rules exist for February
        feb_rules = test_client.get("/api/budget/rules/2024/2").json()
        assert len(feb_rules) == 4

    def test_copy_previous_month_rules_no_source(self, test_client):
        """POST /api/budget/rules/2024/2/copy returns 404 when no previous month rules."""
        response = test_client.post("/api/budget/rules/2024/2/copy")
        assert response.status_code == 404

    def test_get_monthly_analysis(
        self, test_client, seed_budget_rules, seed_base_transactions, monkeypatch
    ):
        """GET /api/budget/analysis/2024/1 returns analysis."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            SAMPLE_CATEGORIES,
        )
        response = test_client.get("/api/budget/analysis/2024/1")
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert "project_spending" in data
        assert "pending_refunds" in data
        assert isinstance(data["rules"], list)
        assert len(data["rules"]) > 0

    def test_get_projects(self, test_client, seed_project_transactions):
        """GET /api/budget/projects returns project names."""
        response = test_client.get("/api/budget/projects")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "Wedding" in data
        assert "Renovation" in data

    def test_create_project(self, test_client, monkeypatch):
        """POST /api/budget/projects creates a project."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            SAMPLE_CATEGORIES,
        )
        payload = {"category": "Housing", "total_budget": 5000.0}
        response = test_client.post("/api/budget/projects", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify the project exists
        projects_response = test_client.get("/api/budget/projects")
        assert "Housing" in projects_response.json()

    def test_delete_project(self, test_client, seed_project_transactions):
        """DELETE /api/budget/projects/{name} deletes a project."""
        response = test_client.delete("/api/budget/projects/Wedding")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify deletion
        projects = test_client.get("/api/budget/projects").json()
        assert "Wedding" not in projects
