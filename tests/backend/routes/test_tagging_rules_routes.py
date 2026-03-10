"""Tests for the /api/tagging-rules API endpoints."""

import pytest

import backend.services.tagging_service as ts
from backend.errors import BadRequestException, EntityNotFoundException
from backend.models.category import Category


@pytest.fixture(autouse=True)
def seed_route_categories(db_session):
    """Seed categories into the DB and reset cache for each route test."""
    ts._categories_cache = None
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
    for name, tags in categories.items():
        db_session.add(Category(name=name, tags=tags))
    db_session.commit()
    yield
    ts._categories_cache = None


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


class TestTaggingRulesRoutesErrors:
    """Tests for error handling in tagging rules route endpoints."""

    # -- POST /rules error paths --

    def test_create_rule_bad_request(self, test_client):
        """Verify 400 when rule creation raises BadRequestException."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.add_rule.side_effect = BadRequestException("Invalid conditions")
            response = test_client.post(
                "/api/tagging-rules/rules",
                json={
                    "name": "Bad Rule",
                    "conditions": {"type": "AND", "subconditions": []},
                    "category": "Food",
                    "tag": "Groceries",
                },
            )
            assert response.status_code == 400
            assert "Invalid conditions" in response.json()["detail"]

    def test_create_rule_internal_error(self, test_client):
        """Verify 500 when rule creation raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.add_rule.side_effect = RuntimeError("Database error")
            response = test_client.post(
                "/api/tagging-rules/rules",
                json={
                    "name": "Error Rule",
                    "conditions": {"type": "AND", "subconditions": []},
                    "category": "Food",
                    "tag": "Groceries",
                },
            )
            assert response.status_code == 500
            assert "Database error" in response.json()["detail"]

    # -- PUT /rules/{id} error paths --

    def test_update_rule_not_found(self, test_client):
        """Verify 404 when updating a rule that does not exist."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_rule.side_effect = EntityNotFoundException(
                "Rule 99999 not found"
            )
            response = test_client.put(
                "/api/tagging-rules/rules/99999",
                json={"name": "Updated Rule"},
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_update_rule_bad_request(self, test_client):
        """Verify 400 when update payload fails validation."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_rule.side_effect = BadRequestException(
                "Invalid rule conditions"
            )
            response = test_client.put(
                "/api/tagging-rules/rules/1",
                json={"conditions": {"type": "INVALID"}},
            )
            assert response.status_code == 400
            assert "Invalid rule conditions" in response.json()["detail"]

    def test_update_rule_internal_error(self, test_client):
        """Verify 500 when update raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_rule.side_effect = RuntimeError("Unexpected failure")
            response = test_client.put(
                "/api/tagging-rules/rules/1",
                json={"name": "New Name"},
            )
            assert response.status_code == 500
            assert "Unexpected failure" in response.json()["detail"]

    # -- POST /rules/apply error path --

    def test_apply_all_rules_internal_error(self, test_client):
        """Verify 500 when apply_rules raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.apply_rules.side_effect = RuntimeError("Apply failed")
            response = test_client.post("/api/tagging-rules/rules/apply")
            assert response.status_code == 500
            assert "Apply failed" in response.json()["detail"]

    # -- POST /rules/{id}/apply paths --

    def test_apply_single_rule_not_found(self, test_client):
        """Verify 404 when applying a rule that does not exist."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.apply_rule_by_id.side_effect = EntityNotFoundException(
                "Rule 99999 not found"
            )
            response = test_client.post("/api/tagging-rules/rules/99999/apply")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_apply_single_rule_internal_error(self, test_client):
        """Verify 500 when applying a single rule raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.apply_rule_by_id.side_effect = RuntimeError(
                "Rule apply exploded"
            )
            response = test_client.post("/api/tagging-rules/rules/1/apply")
            assert response.status_code == 500
            assert "Rule apply exploded" in response.json()["detail"]

    # -- POST /rules/validate error paths --

    def test_validate_rule_conflict(self, test_client):
        """Verify 400 when validation detects a conflict."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_conflicts.side_effect = BadRequestException(
                "Rule conflicts with existing rule"
            )
            response = test_client.post(
                "/api/tagging-rules/rules/validate",
                json={
                    "conditions": {"type": "AND", "subconditions": []},
                    "category": "Food",
                    "tag": "Groceries",
                },
            )
            assert response.status_code == 400
            assert "conflicts" in response.json()["detail"]

    def test_validate_rule_internal_error(self, test_client):
        """Verify 500 when validation raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_conflicts.side_effect = RuntimeError("Validation crash")
            response = test_client.post(
                "/api/tagging-rules/rules/validate",
                json={
                    "conditions": {"type": "AND", "subconditions": []},
                    "category": "Food",
                    "tag": "Groceries",
                },
            )
            assert response.status_code == 500
            assert "Validation crash" in response.json()["detail"]

    # -- POST /rules/preview error paths --

    def test_preview_rule_bad_request(self, test_client):
        """Verify 400 when preview conditions are invalid."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.preview_rule.side_effect = BadRequestException(
                "Invalid conditions format"
            )
            response = test_client.post(
                "/api/tagging-rules/rules/preview",
                json={
                    "conditions": {"type": "INVALID"},
                    "limit": 10,
                },
            )
            assert response.status_code == 400
            assert "Invalid conditions" in response.json()["detail"]

    def test_preview_rule_internal_error(self, test_client):
        """Verify 500 when preview raises an unexpected exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.preview_rule.side_effect = RuntimeError("Preview crashed")
            response = test_client.post(
                "/api/tagging-rules/rules/preview",
                json={
                    "conditions": {"type": "AND", "subconditions": []},
                    "limit": 10,
                },
            )
            assert response.status_code == 500
            assert "Preview crashed" in response.json()["detail"]

    # -- POST /rules/auto-tag-credit-cards-bills --

    def test_auto_tag_credit_cards_bills_success(self, test_client):
        """Verify successful auto-tagging of credit card bills."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.auto_tag_credit_cards_bills.return_value = 5
            response = test_client.post(
                "/api/tagging-rules/rules/auto-tag-credit-cards-bills"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["tagged_count"] == 5

    def test_auto_tag_credit_cards_bills_error(self, test_client):
        """Verify 500 when auto-tag credit card bills raises an exception."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.auto_tag_credit_cards_bills.side_effect = RuntimeError(
                "Auto-tag failed"
            )
            response = test_client.post(
                "/api/tagging-rules/rules/auto-tag-credit-cards-bills"
            )
            assert response.status_code == 500
            assert "Auto-tag failed" in response.json()["detail"]

    def test_auto_tag_credit_cards_bills_zero_tagged(self, test_client):
        """Verify success response when no transactions are auto-tagged."""
        from unittest.mock import patch, MagicMock

        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.auto_tag_credit_cards_bills.return_value = 0
            response = test_client.post(
                "/api/tagging-rules/rules/auto-tag-credit-cards-bills"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["tagged_count"] == 0
