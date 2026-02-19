"""Tests for the /api/tagging-rules API endpoints."""

import pytest


@pytest.fixture(autouse=True)
def mock_categories(monkeypatch):
    """Provide in-memory categories and mock file I/O for tagging rules tests."""
    categories = {
        "Food": ["Groceries", "Restaurants"],
        "Transport": ["Gas", "Public Transport", "Rides"],
        "Entertainment": ["Cinema", "Streaming"],
        "Salary": [],
        "Other Income": [],
        "Investments": [],
        "Ignore": [],
        "Liabilities": [],
        "Credit Cards": [],
        "Housing": ["Rent", "Utilities"],
    }
    monkeypatch.setattr(
        "backend.services.tagging_service._categories_cache", categories
    )
    monkeypatch.setattr(
        "backend.repositories.tagging_repository.TaggingRepository.save_categories_to_file",
        lambda *a, **kw: None,
    )


class TestTaggingRulesRoutes:
    """Tests for tagging rule endpoints."""

    def test_get_tagging_rules(self, test_client, seed_tagging_rules):
        """GET /api/tagging-rules/rules returns all rules."""
        response = test_client.get("/api/tagging-rules/rules")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        names = {r["name"] for r in data}
        assert "Supermarket Rule" in names
        assert "Uber Rule" in names
        assert "Netflix Rule" in names

    def test_create_tagging_rule(self, test_client, seed_untagged_transactions):
        """POST /api/tagging-rules/rules creates a rule and auto-applies."""
        response = test_client.post(
            "/api/tagging-rules/rules",
            json={
                "name": "Pharmacy Rule",
                "conditions": {
                    "type": "AND",
                    "subconditions": [
                        {
                            "type": "CONDITION",
                            "field": "description",
                            "operator": "contains",
                            "value": "PHARMACY",
                        }
                    ],
                },
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "id" in data
        assert data["tagged_count"] >= 1

    def test_update_tagging_rule(self, test_client, seed_tagging_rules):
        """PUT /api/tagging-rules/rules/{id} updates a rule."""
        rule_id = seed_tagging_rules[0].id
        response = test_client.put(
            f"/api/tagging-rules/rules/{rule_id}",
            json={"name": "Updated Supermarket Rule"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_delete_tagging_rule(self, test_client, seed_tagging_rules):
        """DELETE /api/tagging-rules/rules/{id} deletes a rule."""
        rule_id = seed_tagging_rules[0].id
        response = test_client.delete(f"/api/tagging-rules/rules/{rule_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify it was removed
        get_resp = test_client.get("/api/tagging-rules/rules")
        ids = {r["id"] for r in get_resp.json()}
        assert rule_id not in ids

    def test_delete_nonexistent_rule(self, test_client):
        """DELETE /api/tagging-rules/rules/99999 returns 404."""
        response = test_client.delete("/api/tagging-rules/rules/99999")
        assert response.status_code == 404

    def test_apply_all_rules(
        self, test_client, seed_tagging_rules, seed_untagged_transactions
    ):
        """POST /api/tagging-rules/rules/apply applies all rules."""
        response = test_client.post("/api/tagging-rules/rules/apply")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["tagged_count"] >= 1

    def test_preview_rule(self, test_client, seed_untagged_transactions):
        """POST /api/tagging-rules/rules/preview shows matching transactions."""
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={
                "conditions": {
                    "type": "AND",
                    "subconditions": [
                        {
                            "type": "CONDITION",
                            "field": "description",
                            "operator": "contains",
                            "value": "SUPERMARKET",
                        }
                    ],
                },
                "limit": 50,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "matches" in data
        assert "count" in data
        assert data["count"] >= 1
        # All matches should contain SUPERMARKET in description
        for match in data["matches"]:
            assert "SUPERMARKET" in match["description"].upper()

    def test_validate_rule_no_conflict(self, test_client):
        """POST /api/tagging-rules/rules/validate returns valid for non-conflicting rule."""
        response = test_client.post(
            "/api/tagging-rules/rules/validate",
            json={
                "conditions": {
                    "type": "AND",
                    "subconditions": [
                        {
                            "type": "CONDITION",
                            "field": "description",
                            "operator": "contains",
                            "value": "UNIQUE_STRING_NO_MATCH",
                        }
                    ],
                },
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "valid"
