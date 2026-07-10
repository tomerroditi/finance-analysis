"""Tests for the /api/budget/yearly API endpoints."""


class TestYearlyBudgetRoutes:
    """Yearly budget HTTP endpoints."""

    def test_create_and_get_yearly_rule(self, test_client):
        """POST creates a rule; GET analysis returns it under 'rules'."""
        r = test_client.post("/api/budget/yearly/rules", json={
            "name": "Vacations", "amount": 20000, "category": "Travel",
            "tags": ["Hotels"], "year": 2026})
        assert r.status_code == 200
        data = test_client.get("/api/budget/yearly/2026/analysis").json()
        names = [e["rule"]["name"] for e in data["rules"]]
        assert "Vacations" in names
        assert "summary" in data and "carried_from" in data

    def test_conflict_returns_400(self, test_client):
        """A yearly rule reusing a monthly tag for the year is 400."""
        test_client.post("/api/budget/rules", json={
            "name": "Total Budget", "amount": 9999, "category": "Total Budget",
            "tags": ["all_tags"], "month": 5, "year": 2026})
        test_client.post("/api/budget/rules", json={
            "name": "Food M", "amount": 500, "category": "Food",
            "tags": ["Groceries"], "month": 5, "year": 2026})
        r = test_client.post("/api/budget/yearly/rules", json={
            "name": "Food Y", "amount": 6000, "category": "Food",
            "tags": ["Groceries"], "year": 2026})
        assert r.status_code == 400
        assert "Groceries" in r.json()["detail"]

    def test_get_yearly_view_empty(self, test_client):
        """GET /yearly/{year} returns an empty rules list when there are none."""
        r = test_client.get("/api/budget/yearly/2030")
        assert r.status_code == 200
        assert r.json() == {"rules": []}

    def test_update_yearly_rule(self, test_client):
        """PUT /yearly/rules/{id} updates the rule's amount."""
        test_client.post("/api/budget/yearly/rules", json={
            "name": "Vacations", "amount": 20000, "category": "Travel",
            "tags": ["Hotels"], "year": 2027})
        rules = test_client.get("/api/budget/yearly/2027/analysis").json()["rules"]
        rule_id = rules[0]["rule"]["id"]

        r = test_client.put(f"/api/budget/yearly/rules/{rule_id}", json={"amount": 25000})
        assert r.status_code == 200

        rules = test_client.get("/api/budget/yearly/2027/analysis").json()["rules"]
        assert rules[0]["rule"]["amount"] == 25000

    def test_delete_yearly_rule(self, test_client):
        """DELETE /yearly/rules/{id} removes the rule."""
        test_client.post("/api/budget/yearly/rules", json={
            "name": "Vacations", "amount": 20000, "category": "Travel",
            "tags": ["Hotels"], "year": 2028})
        rules = test_client.get("/api/budget/yearly/2028/analysis").json()["rules"]
        rule_id = rules[0]["rule"]["id"]

        r = test_client.delete(f"/api/budget/yearly/rules/{rule_id}")
        assert r.status_code == 200

        rules = test_client.get("/api/budget/yearly/2028/analysis").json()["rules"]
        assert rules == []

    def test_yearly_alerts(self, test_client):
        """GET /yearly/alerts/{year} returns an alerts payload."""
        r = test_client.get("/api/budget/yearly/alerts/2029")
        assert r.status_code == 200
        data = r.json()
        assert data["year"] == 2029
        assert data["alerts"] == []

    def test_copy_previous_year_no_source_returns_404(self, test_client):
        """POST /yearly/{year}/copy returns 404 when there is no prior year to copy."""
        r = test_client.post("/api/budget/yearly/2031/copy")
        assert r.status_code == 404


class TestMonthlyEditYearlyConflictRoute:
    """Editing a monthly rule to claim a yearly-owned tag must be rejected."""

    def test_edit_monthly_rule_adding_yearly_conflicting_tag_returns_400(self, test_client):
        """PUT /budget/rules/{id} adding a tag already owned by a yearly rule is 400."""
        test_client.post("/api/budget/yearly/rules", json={
            "name": "Vacations", "amount": 20000, "category": "Travel",
            "tags": ["Hotels"], "year": 2026})
        test_client.post("/api/budget/rules", json={
            "name": "Total Budget", "amount": 9999, "category": "Total Budget",
            "tags": ["all_tags"], "month": 5, "year": 2026})
        test_client.post("/api/budget/rules", json={
            "name": "Travel M", "amount": 500, "category": "Travel",
            "tags": ["Car rental"], "month": 5, "year": 2026})

        month_rules = test_client.get("/api/budget/rules/2026/5").json()
        travel_rule = next(r for r in month_rules if r["name"] == "Travel M")

        r = test_client.put(
            f"/api/budget/rules/{travel_rule['id']}",
            json={"tags": ["Car rental", "Hotels"]},
        )
        assert r.status_code == 400
        assert "Hotels" in r.json()["detail"]

    def test_edit_project_rule_via_shared_route_still_works(
        self, test_client, monkeypatch
    ):
        """Regression: PUT /budget/rules/{id} still edits project rules.

        The route is shared between monthly and project rules. Wiring it to
        MonthlyBudgetService must not break editing a project's tag rules —
        project rules have no year and must skip the yearly-conflict guard.
        """
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {"Wedding": ["Venue", "Catering"]},
        )
        test_client.post(
            "/api/budget/projects", json={"category": "Wedding", "total_budget": 10000.0}
        )
        project_rules = test_client.get("/api/budget/projects/Wedding").json()["rules"]
        venue_rule = next(
            e for e in project_rules if e["rule"]["name"] == "Venue"
        )["rule"]

        r = test_client.put(
            f"/api/budget/rules/{venue_rule['id']}", json={"amount": 3000.0}
        )
        assert r.status_code == 200

        updated_rules = test_client.get("/api/budget/projects/Wedding").json()["rules"]
        updated_venue = next(e for e in updated_rules if e["rule"]["name"] == "Venue")
        assert updated_venue["rule"]["amount"] == 3000.0
