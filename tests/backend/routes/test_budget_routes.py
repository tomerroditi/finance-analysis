"""Tests for the /api/budget API endpoints (happy paths).

Error and not-found paths live in ``test_budget_routes_errors.py``.
"""

from backend.constants.budget import ALL_TAGS, TOTAL_BUDGET
from backend.models.budget import BudgetRule


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
        assert response.json()["message"] == "Copied 4 rules from 2024-1"
        feb_rules = test_client.get("/api/budget/rules/2024/2").json()
        assert len(feb_rules) == 4

    def test_get_monthly_analysis(
        self, test_client, seed_budget_rules, seed_base_transactions, monkeypatch
    ):
        """GET /api/budget/analysis/2024/1 returns spend per seeded rule.

        January 2024 spend from ``seed_base_transactions``: Food 245,
        Transport 70, Entertainment 40, everything 3605; the Home rent
        (3000) and Other (250) land in Other Expenses with the
        10000 - 2800 = 7200 of unallocated headroom.
        """
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        response = test_client.get("/api/budget/analysis/2024/1")
        assert response.status_code == 200
        data = response.json()
        assert data["project_spending"] == {"projects": []}
        assert data["pending_refunds"] == {"items": [], "total_expected": 0.0}
        assert data["copied_from"] is None
        assert data["skipped_yearly_conflicts"] == []

        by_name = {e["rule"]["name"]: e for e in data["rules"]}
        assert set(by_name) == {
            TOTAL_BUDGET, "Food", "Transport", "Entertainment", "Other Expenses"
        }
        assert by_name[TOTAL_BUDGET]["current_amount"] == 3605.0
        assert by_name[TOTAL_BUDGET]["allow_delete"] is False
        assert by_name["Food"]["current_amount"] == 245.0
        assert by_name["Food"]["rule"]["tags"] == [ALL_TAGS]
        assert by_name["Transport"]["current_amount"] == 70.0
        assert by_name["Entertainment"]["current_amount"] == 40.0
        assert by_name["Other Expenses"]["current_amount"] == 3250.0
        assert by_name["Other Expenses"]["rule"]["amount"] == 7200.0

    def test_get_month_alerts(
        self, test_client, seed_base_transactions, monkeypatch
    ):
        """GET /api/budget/alerts/{year}/{month} returns alerts payload."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        # Seed a tight Food budget that will be tripped by Jan 2024 transactions.
        test_client.post(
            "/api/budget/rules",
            json={
                "name": "Total Budget",
                "amount": 10000.0,
                "category": "Total Budget",
                "tags": ["all_tags"],
                "year": 2024,
                "month": 1,
            },
        )
        test_client.post(
            "/api/budget/rules",
            json={
                "name": "Food",
                "amount": 200.0,
                "category": "Food",
                "tags": ["all_tags"],
                "year": 2024,
                "month": 1,
            },
        )

        response = test_client.get("/api/budget/alerts/2024/1")
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2024
        assert data["month"] == 1
        assert isinstance(data["alerts"], list)
        assert len(data["alerts"]) == 1
        food_alert = data["alerts"][0]
        assert food_alert["category"] == "Food"
        assert food_alert["severity"] == "critical"

    def test_get_current_month_alerts_returns_payload(
        self, test_client, monkeypatch
    ):
        """GET /api/budget/alerts returns current-month payload, even when empty."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        response = test_client.get("/api/budget/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "year" in data
        assert "month" in data
        assert data["alerts"] == []

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
            {False: SAMPLE_CATEGORIES},
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


class TestCategoryConflictsRoutes:
    """Category-level project ↔ monthly/yearly conflict surfacing + block."""

    def test_create_project_on_budget_category_returns_400(self, test_client):
        """POST /budget/projects on a monthly-used category is 400."""
        test_client.post("/api/budget/rules", json={
            "name": "Total Budget", "amount": 9999, "category": "Total Budget", "tags": ["all_tags"], "month": 5, "year": 2026})
        test_client.post("/api/budget/rules", json={
            "name": "Food M", "amount": 500, "category": "Food", "tags": ["Groceries"], "month": 5, "year": 2026})
        r = test_client.post("/api/budget/projects", json={"category": "Food", "total_budget": 5000})
        assert r.status_code == 400
        assert "Food" in r.json()["detail"]

    def test_category_conflicts_endpoint(self, test_client, db_session):
        """GET /budget/category-conflicts reports a category that is both
        project-owned and monthly-budgeted, and nothing else.

        The API blocks creating such an overlap, so it is seeded directly
        (data predating the exclusion rule looks exactly like this).
        """
        db_session.add_all(
            [
                BudgetRule(
                    name=TOTAL_BUDGET, amount=5000.0, category="Renovation",
                    tags=ALL_TAGS, year=None, month=None, period_type="project",
                ),
                BudgetRule(
                    name="Reno M", amount=500.0, category="Renovation",
                    tags="Materials", year=2026, month=5, period_type="monthly",
                ),
                BudgetRule(
                    name="Food M", amount=500.0, category="Food",
                    tags="Groceries", year=2026, month=5, period_type="monthly",
                ),
            ]
        )
        db_session.commit()

        r = test_client.get("/api/budget/category-conflicts")
        assert r.status_code == 200
        assert r.json() == {
            "conflicts": [{"category": "Renovation", "kinds": ["monthly"]}]
        }

    def test_shared_put_route_rejects_project_category_change_to_budget_used(
        self, test_client, monkeypatch
    ):
        """PUT /budget/rules/{id} must reject changing a PROJECT rule's category
        to one already claimed by a monthly/yearly budget.

        The route is shared between monthly and project rule edits. Project
        rules have ``year = NaN``, which previously fell through the
        service's category guard entirely, letting a raw PUT create the same
        project/budget category overlap ``POST /budget/projects`` blocks.
        """
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        test_client.post("/api/budget/rules", json={
            "name": "Total Budget", "amount": 9999, "category": "Total Budget",
            "tags": ["all_tags"], "month": 5, "year": 2026,
        })
        test_client.post("/api/budget/rules", json={
            "name": "Food M", "amount": 500, "category": "Food",
            "tags": ["Groceries"], "month": 5, "year": 2026,
        })
        project_resp = test_client.post(
            "/api/budget/projects", json={"category": "Renovation", "total_budget": 5000}
        )
        assert project_resp.status_code == 200

        rules = test_client.get("/api/budget/rules").json()
        project_rule = next(
            r for r in rules if r["category"] == "Renovation" and r["year"] is None
        )

        r = test_client.put(
            f"/api/budget/rules/{project_rule['id']}",
            json={"category": "Food", "tags": ["Materials"]},
        )
        assert r.status_code == 400
        assert "Food" in r.json()["detail"]

        # No overlap was created — the project rule's category is unchanged.
        unchanged = test_client.get("/api/budget/rules").json()
        unchanged_rule = next(r for r in unchanged if r["id"] == project_rule["id"])
        assert unchanged_rule["category"] == "Renovation"
