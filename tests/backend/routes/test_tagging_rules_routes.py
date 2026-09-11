"""Tests for the /api/tagging-rules API endpoints."""

from unittest.mock import MagicMock, patch

import pytest

import backend.services.tagging_service as ts
from backend.errors import BadRequestException, EntityNotFoundException
from backend.models.category import Category
from backend.models.tagging_rules import TaggingRule


@pytest.fixture(autouse=True)
def seed_route_categories(db_session):
    """Seed categories into the DB and reset cache for each route test."""
    ts._categories_cache = {}
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
    ts._categories_cache = {}


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
        # Exactly one seeded transaction says PHARMACY (cc_untag_4).
        assert data["tagged_count"] == 1

    def test_update_tagging_rule(self, test_client, seed_tagging_rules):
        """PUT /api/tagging-rules/rules/{id} persists the new field values."""
        rule_id = seed_tagging_rules[0].id
        response = test_client.put(
            f"/api/tagging-rules/rules/{rule_id}",
            json={"name": "Updated Supermarket Rule", "tag": "Restaurants"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        rules = test_client.get("/api/tagging-rules/rules").json()
        updated = next(r for r in rules if r["id"] == rule_id)
        assert updated["name"] == "Updated Supermarket Rule"
        assert updated["tag"] == "Restaurants"
        assert updated["category"] == "Food"

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
        """POST /api/tagging-rules/rules/apply tags every matching transaction.

        The three seeded rules (SUPERMARKET, UBER, Netflix) each match one CC
        and one bank transaction in ``seed_untagged_transactions``; the
        PHARMACY and wire-transfer rows match nothing.
        """
        response = test_client.post("/api/tagging-rules/rules/apply")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["tagged_count"] == 6

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
        assert data["count"] == 2
        # All matches should contain SUPERMARKET in description
        for match in data["matches"]:
            assert "SUPERMARKET" in match["description"].upper()

    def test_validate_rule_no_conflict(
        self, test_client, seed_tagging_rules, seed_untagged_transactions
    ):
        """POST /rules/validate accepts a rule that overlaps no existing rule.

        Conflict detection returns early when the candidate matches nothing,
        so the rule under test deliberately DOES match seeded transactions
        (PHARMACY) — just not the same ones as any of the three seeded rules.
        That way the whole per-rule overlap loop actually runs.
        """
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
                            "value": "PHARMACY",
                        }
                    ],
                },
                "category": "Food",
                "tag": "Groceries",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "valid"

    def test_validate_rule_reports_an_overlap(
        self, test_client, seed_tagging_rules, seed_untagged_transactions
    ):
        """A rule matching another rule's transactions with a different pair is 400."""
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
                            "value": "SUPERMARKET",
                        }
                    ],
                },
                "category": "Entertainment",
                "tag": "Cinema",
            },
        )
        assert response.status_code == 400
        assert "Conflict detected" in response.json()["detail"]


class TestTaggingRulesRoutesErrors:
    """Service exceptions map to HTTP status codes, one endpoint at a time.

    Every rule endpoint goes through the same global handlers, so the
    per-endpoint copies of "this exception becomes this status" are
    parametrized rather than written out seven times.
    """

    # (label, http method, path, body, service method the route calls)
    ENDPOINTS = [
        (
            "create",
            "post",
            "/api/tagging-rules/rules",
            {
                "name": "Rule",
                "conditions": {"type": "AND", "subconditions": []},
                "category": "Food",
                "tag": "Groceries",
            },
            "add_rule",
        ),
        ("update", "put", "/api/tagging-rules/rules/1", {"name": "New Name"}, "update_rule"),
        ("apply-all", "post", "/api/tagging-rules/rules/apply", None, "apply_rules"),
        ("apply-one", "post", "/api/tagging-rules/rules/1/apply", None, "apply_rule_by_id"),
        (
            "validate",
            "post",
            "/api/tagging-rules/rules/validate",
            {
                "conditions": {"type": "AND", "subconditions": []},
                "category": "Food",
                "tag": "Groceries",
            },
            "check_conflicts",
        ),
        (
            "preview",
            "post",
            "/api/tagging-rules/rules/preview",
            {"conditions": {"type": "AND", "subconditions": []}, "limit": 10},
            "preview_rule",
        ),
        (
            "auto-tag-cc",
            "post",
            "/api/tagging-rules/rules/auto-tag-credit-cards-bills",
            None,
            "auto_tag_credit_cards_bills",
        ),
    ]

    @staticmethod
    def _call(client, method, path, body, service_method, exc):
        """Make the request with the route's service method raising ``exc``."""
        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            getattr(mock_svc, service_method).side_effect = exc
            kwargs = {"json": body} if body is not None else {}
            return getattr(client, method)(path, **kwargs)

    @pytest.mark.parametrize(
        "method, path, body, service_method",
        [entry[1:] for entry in ENDPOINTS],
        ids=[entry[0] for entry in ENDPOINTS],
    )
    def test_unexpected_exception_is_an_opaque_500(
        self, test_client_no_raise, method, path, body, service_method
    ):
        """An unexpected error becomes a 500 whose body leaks no internals."""
        response = self._call(
            test_client_no_raise, method, path, body, service_method,
            RuntimeError("psycopg: relation \"secret\" does not exist"),
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    @pytest.mark.parametrize(
        "method, path, body, service_method",
        [entry[1:] for entry in ENDPOINTS if entry[0] != "auto-tag-cc"],
        ids=[entry[0] for entry in ENDPOINTS if entry[0] != "auto-tag-cc"],
    )
    def test_bad_request_is_a_400_with_its_message(
        self, test_client_no_raise, method, path, body, service_method
    ):
        """``BadRequestException`` becomes a 400 carrying the service's message."""
        response = self._call(
            test_client_no_raise, method, path, body, service_method,
            BadRequestException("Invalid conditions"),
        )

        assert response.status_code == 400
        assert "Invalid conditions" in response.json()["detail"]

    @pytest.mark.parametrize(
        "method, path, body, service_method",
        [
            ("put", "/api/tagging-rules/rules/99999", {"name": "X"}, "update_rule"),
            ("post", "/api/tagging-rules/rules/99999/apply", None, "apply_rule_by_id"),
        ],
        ids=["update", "apply-one"],
    )
    def test_missing_rule_is_a_404(
        self, test_client_no_raise, method, path, body, service_method
    ):
        """``EntityNotFoundException`` becomes a 404."""
        response = self._call(
            test_client_no_raise, method, path, body, service_method,
            EntityNotFoundException("Rule 99999 not found"),
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.parametrize("count", [5, 0])
    def test_auto_tag_credit_cards_bills_reports_its_count(
        self, test_client_no_raise, count
    ):
        """The auto-tag endpoint echoes the service's count, zero included."""
        with patch("backend.routes.tagging_rules.TaggingRulesService") as mock_cls:
            mock_svc = MagicMock()
            mock_cls.return_value = mock_svc
            mock_svc.auto_tag_credit_cards_bills.return_value = count
            response = test_client_no_raise.post(
                "/api/tagging-rules/rules/auto-tag-credit-cards-bills"
            )

        assert response.status_code == 200
        assert response.json() == {"status": "success", "tagged_count": count}


class TestApplySingleRuleOverwrite:
    """POST /rules/{id}/apply?overwrite=true against a real DB."""

    def test_overwrite_resets_a_matching_transaction(
        self, test_client, db_session, seed_untagged_transactions
    ):
        """``overwrite=true`` re-tags a row that already carries another pair.

        Without the flag the same call is a no-op, which is what makes the
        two requests worth asserting back to back.
        """
        from backend.models.transaction import CreditCardTransaction
        from sqlalchemy import select

        row = db_session.execute(
            select(CreditCardTransaction).where(
                CreditCardTransaction.id == "cc_untag_1"
            )
        ).scalar_one()
        row.category, row.tag = "Entertainment", "Cinema"
        db_session.add(
            TaggingRule(
                name="Supermarket",
                conditions={
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": "SUPERMARKET PURCHASE",
                },
                category="Food",
                tag="Groceries",
            )
        )
        db_session.commit()
        rule_id = test_client.get("/api/tagging-rules/rules").json()[0]["id"]

        without = test_client.post(f"/api/tagging-rules/rules/{rule_id}/apply")
        assert without.status_code == 200
        assert without.json()["tagged_count"] == 0

        response = test_client.post(
            f"/api/tagging-rules/rules/{rule_id}/apply?overwrite=true"
        )
        assert response.status_code == 200
        assert response.json() == {"status": "success", "tagged_count": 1}

        db_session.expire_all()
        row = db_session.execute(
            select(CreditCardTransaction).where(
                CreditCardTransaction.id == "cc_untag_1"
            )
        ).scalar_one()
        assert (row.category, row.tag) == ("Food", "Groceries")


class TestPreviewAndValidateConditionIntegrity:
    """Malformed conditions yield 400, never 500 — on both read endpoints."""

    BAD_CONDITIONS = [
        ("non-numeric", {"field": "amount", "operator": "gt", "value": "abc"}),
        ("null-numeric", {"field": "amount", "operator": "gt", "value": None}),
        ("short-between", {"field": "amount", "operator": "between", "value": [1]}),
        ("blank-text", {"field": "description", "operator": "contains", "value": " "}),
        ("unknown-field", {"field": "descripton", "operator": "contains", "value": "x"}),
    ]

    @pytest.mark.parametrize(
        "leaf",
        [entry[1] for entry in BAD_CONDITIONS],
        ids=[entry[0] for entry in BAD_CONDITIONS],
    )
    @pytest.mark.parametrize("endpoint", ["preview", "validate"])
    def test_malformed_condition_is_a_400(self, test_client_no_raise, endpoint, leaf):
        """Each malformed leaf is rejected with 400 by preview and validate."""
        body = {"conditions": {"type": "CONDITION", **leaf}}
        if endpoint == "validate":
            body |= {"category": "Food", "tag": "Groceries"}

        response = test_client_no_raise.post(
            f"/api/tagging-rules/rules/{endpoint}", json=body
        )

        assert response.status_code == 400

    def test_valid_conditions_still_preview(
        self, test_client, seed_untagged_transactions
    ):
        """A well-formed numeric condition still previews successfully."""
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={
                "conditions": {
                    "type": "CONDITION",
                    "field": "amount",
                    "operator": "gt",
                    "value": -1000000,
                }
            },
        )
        assert response.status_code == 200


class TestPreviewLimitBounds:
    """Tests for the bounded ``limit`` field on the preview endpoint."""

    def _conditions(self):
        """Build a condition matching every seeded description.

        A blank pattern would be the natural "match everything" value but it
        is now rejected as a catch-all, so this matches on a letter every
        seeded description happens to contain.
        """
        return {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "e",
        }

    def test_negative_limit_is_rejected(self, test_client):
        """POST /rules/preview with limit=-1 returns 422.

        A negative limit made SQLite ignore the LIMIT clause while pandas
        ``head(-1)`` silently dropped the last row.
        """
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={"conditions": self._conditions(), "limit": -1},
        )
        assert response.status_code == 422

    def test_zero_limit_is_rejected(self, test_client):
        """POST /rules/preview with limit=0 returns 422."""
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={"conditions": self._conditions(), "limit": 0},
        )
        assert response.status_code == 422

    def test_excessive_limit_is_rejected(self, test_client):
        """POST /rules/preview with limit above the cap returns 422."""
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={"conditions": self._conditions(), "limit": 5000},
        )
        assert response.status_code == 422

    def test_omitted_limit_defaults_to_bounded_value(
        self, test_client, seed_untagged_transactions
    ):
        """POST /rules/preview without a limit uses the bounded default."""
        response = test_client.post(
            "/api/tagging-rules/rules/preview",
            json={"conditions": self._conditions()},
        )
        assert response.status_code == 200
        assert response.json()["count"] <= 100
