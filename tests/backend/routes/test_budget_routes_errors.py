"""Tests for error/negative paths in the /api/budget API endpoints.

Covers validation errors, not-found scenarios, duplicate detection and
sanitized 500s for budget rules and project budget endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.constants.budget import TOTAL_BUDGET

SAMPLE_CATEGORIES = {
    "Food": ["Groceries", "Restaurants"],
    "Wedding": ["Venue", "Catering"],
    "Renovation": ["Materials", "Labor"],
}


class TestBudgetRuleValidationErrors:
    """Tests for Pydantic validation and business-rule errors on budget endpoints."""

    @pytest.mark.parametrize(
        "month, year",
        [(13, 2024), (0, 2024), (1, -1), (1, 1999), (1, 2101)],
        ids=["month-13", "month-0", "year-negative", "year-too-early", "year-too-late"],
    )
    def test_create_budget_rule_out_of_range_period_returns_422(
        self, test_client, month, year
    ):
        """POST /api/budget/rules rejects a month outside 1-12 or a year outside
        2000-2100 at the schema, so no row is ever written for a typo."""
        payload = {
            "name": "Total Budget", "amount": 100.0, "category": "Total Budget",
            "tags": ["all_tags"], "month": month, "year": year,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422
        assert test_client.get("/api/budget/rules").json() == []

    @pytest.mark.parametrize(
        "period", [{"year": 2024}, {"month": 3}], ids=["year-only", "month-only"]
    )
    def test_create_budget_rule_month_without_year_returns_422(self, test_client, period):
        """POST /api/budget/rules needs month and year together.

        A year alone would mint a yearly row through the monthly endpoint,
        bypassing the yearly service's validation.
        """
        payload = {
            "name": "Total Budget", "amount": 100.0, "category": "Total Budget",
            "tags": ["all_tags"], **period,
        }
        response = test_client.post("/api/budget/rules", json=payload)
        assert response.status_code == 422
        assert "together" in str(response.json()["detail"])
        assert test_client.get("/api/budget/rules").json() == []

    @pytest.mark.parametrize(
        "path",
        [
            "/api/budget/rules/2024/13",
            "/api/budget/rules/2024/0",
            "/api/budget/rules/-1/1",
            "/api/budget/analysis/2024/13",
            "/api/budget/alerts/2024/0",
            "/api/budget/yearly/-1",
            "/api/budget/yearly/-1/analysis",
        ],
    )
    def test_get_out_of_range_period_returns_422(self, test_client, path):
        """GET endpoints keyed by year/month 422 on out-of-range path params."""
        assert test_client.get(path).status_code == 422

    def test_copy_out_of_range_month_returns_422(self, test_client):
        """POST /api/budget/rules/{year}/{month}/copy 422s on month 13."""
        assert test_client.post("/api/budget/rules/2024/13/copy").status_code == 422

    @pytest.mark.parametrize("threshold", [1.5, -0.1])
    def test_alerts_threshold_out_of_bounds_returns_422(self, test_client, threshold):
        """GET /api/budget/alerts{,/{y}/{m}} bound ``threshold`` to [0, 1]."""
        assert (
            test_client.get("/api/budget/alerts", params={"threshold": threshold}).status_code
            == 422
        )
        assert (
            test_client.get(
                "/api/budget/alerts/2024/1", params={"threshold": threshold}
            ).status_code
            == 422
        )

    @pytest.mark.parametrize(
        "tags", [["Groceries;Restaurants"], [""], ["Groceries", "  "]],
        ids=["semicolon", "blank", "mixed-blank"],
    )
    def test_create_budget_rule_malformed_tags_returns_400(
        self, test_client, seed_budget_rules, tags
    ):
        """POST /api/budget/rules with a ';' inside a tag or a blank tag is 400."""
        response = test_client.post(
            "/api/budget/rules",
            json={
                "name": "Home", "amount": 100.0, "category": "Home",
                "tags": tags, "month": 1, "year": 2024,
            },
        )
        assert response.status_code == 400
        assert "tag" in response.json()["detail"].lower()

    def test_create_budget_rule_whitespace_name_returns_400(
        self, test_client, seed_budget_rules
    ):
        """POST /api/budget/rules with a whitespace-only name is 400 (empty name)."""
        response = test_client.post(
            "/api/budget/rules",
            json={
                "name": "   ", "amount": 100.0, "category": "Home",
                "tags": ["Rent"], "month": 1, "year": 2024,
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Please enter a name"

    def test_create_specific_tag_under_all_tags_rule_is_allowed(
        self, test_client, seed_budget_rules
    ):
        """POST /api/budget/rules for Food/Groceries succeeds under a Food all_tags rule.

        A sub-budget inside a category the user already budgets as a whole is
        a legitimate shape, and the shipped demo data uses it. The monthly
        view does not yet split spend between the two rules, but refusing the
        rule would remove the feature rather than fix the view.
        """
        response = test_client.post(
            "/api/budget/rules",
            json={
                "name": "Groceries", "amount": 100.0, "category": "Food",
                "tags": ["Groceries"], "month": 1, "year": 2024,
            },
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "payload, expected",
        [
            ({"amount": 0}, "positive"),
            ({"amount": -10}, "positive"),
            ({"name": "   "}, "name"),
            ({"name": "Transport"}, "already exists"),
            ({"amount": 9500}, "exceeded"),
            ({"tags": ["Groceries;Restaurants"]}, "';'"),
            ({"tags": [""]}, "empty"),
        ],
        ids=[
            "zero-amount", "negative-amount", "blank-name", "duplicate-name",
            "over-cap", "semicolon-tag", "blank-tag",
        ],
    )
    def test_update_budget_rule_invalid_returns_400(
        self, test_client, seed_budget_rules, payload, expected
    ):
        """PUT /api/budget/rules/{id} enforces create-time validation on edits.

        Food (2000) sits under a 10000 Total Budget with Transport (500) and
        Entertainment (300); every payload is rejected and the row is untouched.
        """
        rules = test_client.get("/api/budget/rules/2024/1").json()
        food = next(r for r in rules if r["name"] == "Food")

        response = test_client.put(f"/api/budget/rules/{food['id']}", json=payload)
        assert response.status_code == 400
        assert expected in response.json()["detail"]

        after = next(
            r for r in test_client.get("/api/budget/rules/2024/1").json()
            if r["id"] == food["id"]
        )
        assert (after["name"], after["amount"], after["tags"]) == ("Food", 2000.0, ["all_tags"])

    def test_update_total_budget_below_rules_returns_400(
        self, test_client, seed_budget_rules
    ):
        """PUT /api/budget/rules/{id} can't lower the Total Budget under its rules' sum."""
        rules = test_client.get("/api/budget/rules/2024/1").json()
        total = next(r for r in rules if r["name"] == TOTAL_BUDGET)
        response = test_client.put(f"/api/budget/rules/{total['id']}", json={"amount": 2000})
        assert response.status_code == 400
        assert "greater" in response.json()["detail"]

    def test_delete_total_budget_rule_returns_400(self, test_client, seed_budget_rules):
        """DELETE /api/budget/rules/{id} refuses the month's Total Budget rule.

        The view already reports it with ``allow_delete=False``; the API now
        enforces it so a raw call can't orphan the month's category rules.
        """
        rules = test_client.get("/api/budget/rules/2024/1").json()
        total = next(r for r in rules if r["name"] == TOTAL_BUDGET)

        response = test_client.delete(f"/api/budget/rules/{total['id']}")
        assert response.status_code == 400
        assert "Total Budget" in response.json()["detail"]
        assert len(test_client.get("/api/budget/rules/2024/1").json()) == 4

    def test_delete_project_total_rule_returns_400(
        self, test_client, seed_project_transactions
    ):
        """DELETE /api/budget/rules/{id} refuses a project's all_tags total rule."""
        rules = test_client.get("/api/budget/rules").json()
        total = next(
            r for r in rules if r["category"] == "Wedding" and r["tags"] == ["all_tags"]
        )
        response = test_client.delete(f"/api/budget/rules/{total['id']}")
        assert response.status_code == 400
        assert "Wedding" in test_client.get("/api/budget/projects").json()

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
        """Verify updating a non-existent budget rule returns 404.

        The budget repository raises EntityNotFoundException when no rule
        matches the given ID; the global handler maps it to a 404.
        """
        response = test_client.put(
            "/api/budget/rules/99999",
            json={"amount": 5000.0},
        )
        assert response.status_code == 404
        assert "No rule found" in response.json()["detail"]

    def test_update_nonexistent_budget_rule_empty_body(self, test_client):
        """PUT /api/budget/rules/99999 with ``{}`` is still 404.

        The repository used to return before its existence check when there
        were no fields to change, reporting success for a rule that never
        existed.
        """
        response = test_client.put("/api/budget/rules/99999", json={})
        assert response.status_code == 404
        assert "No rule found" in response.json()["detail"]

    def test_delete_nonexistent_budget_rule(self, test_client):
        """DELETE /api/budget/rules/99999 for a non-existent rule returns 404.

        The repository raises EntityNotFoundException (mapped to 404 by the
        global handler) instead of silently succeeding.
        """
        response = test_client.delete("/api/budget/rules/99999")
        assert response.status_code == 404
        assert "No rule found" in response.json()["detail"]

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

    def test_create_duplicate_project_returns_409(
        self, test_client, seed_project_transactions, monkeypatch
    ):
        """POST /api/budget/projects on an existing project's category is 409
        and leaves the existing rule set untouched."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        before = test_client.get("/api/budget/rules").json()

        response = test_client.post(
            "/api/budget/projects", json={"category": "Wedding", "total_budget": 1.0}
        )
        assert response.status_code == 409
        assert "Wedding" in response.json()["detail"]
        assert test_client.get("/api/budget/rules").json() == before

    def test_create_project_unknown_category_returns_400(self, test_client, monkeypatch):
        """POST /api/budget/projects on a category that doesn't exist is 400,
        not a 500 from the tag lookup, and writes no rules."""
        monkeypatch.setattr(
            "backend.services.tagging_service._categories_cache",
            {False: SAMPLE_CATEGORIES},
        )
        response = test_client.post(
            "/api/budget/projects", json={"category": "Nope", "total_budget": 100.0}
        )
        assert response.status_code == 400
        assert "Nope" in response.json()["detail"]
        assert test_client.get("/api/budget/rules").json() == []
        assert test_client.get("/api/budget/projects").json() == []

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
        """Verify a missing project returns ``404 Not Found``.

        The project service raises ``ValueError`` when no rules exist for
        the given category; the route catches that and surfaces it as a
        404 with the same message in ``detail``.
        """
        response = test_client.get("/api/budget/projects/NonExistentProject")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    # Missing-project delete/update behaviour is covered by
    # ``TestProjectNotFoundErrors`` below (both now 404).


class TestProjectNotFoundErrors:
    """Tests that project endpoints 404 on unknown project names."""

    def test_delete_nonexistent_project_returns_404(self, test_client):
        """DELETE /api/budget/projects/{name} for an unknown project returns 404.

        The endpoint used to report ``{"status": "success"}`` for a project
        that never existed, masking typos and stale UI state.
        """
        response = test_client.delete("/api/budget/projects/doesnotexist")
        assert response.status_code == 404
        assert "doesnotexist" in response.json()["detail"]

    def test_update_nonexistent_project_returns_404(self, test_client):
        """PUT /api/budget/projects/{name} for an unknown project returns 404.

        The service raised a bare ``ValueError`` that reached the global
        handler as a 500.
        """
        response = test_client.put(
            "/api/budget/projects/nope", json={"total_budget": 1000.0}
        )
        assert response.status_code == 404


class TestProjectRoutesUnhandledErrors:
    """Unexpected service failures surface as a sanitized 500.

    The global handler must never echo the exception text — it can carry SQL
    fragments, file paths or secrets — so the body is the opaque
    ``Internal server error`` and the real message stays in the log.
    """

    OPAQUE = {"detail": "Internal server error"}

    def _mock_project_service(self, **side_effects):
        mock_svc = MagicMock()
        # The update/delete routes 404 on an unknown project before calling
        # the service; make "Wedding" look real.
        mock_svc.get_all_projects_names.return_value = ["Wedding"]
        for method, exc in side_effects.items():
            getattr(mock_svc, method).side_effect = exc
        return mock_svc

    def test_get_project_details_error_returns_opaque_500(self, test_client_no_raise):
        """GET /api/budget/projects/{name} maps a RuntimeError to an opaque 500."""
        with patch("backend.routes.budget.ProjectBudgetService") as mock_cls:
            mock_cls.return_value = self._mock_project_service(
                get_project_budget_view=RuntimeError("secret /path/to/data.db")
            )
            response = test_client_no_raise.get("/api/budget/projects/Wedding")
        assert response.status_code == 500
        assert response.json() == self.OPAQUE

    def test_delete_project_error_returns_opaque_500(self, test_client_no_raise):
        """DELETE /api/budget/projects/{name} maps a RuntimeError to an opaque 500."""
        with patch("backend.routes.budget.ProjectBudgetService") as mock_cls:
            mock_cls.return_value = self._mock_project_service(
                delete_project=RuntimeError("secret /path/to/data.db")
            )
            response = test_client_no_raise.delete("/api/budget/projects/Wedding")
        assert response.status_code == 500
        assert response.json() == self.OPAQUE

    def test_update_project_error_returns_opaque_500(self, test_client_no_raise):
        """PUT /api/budget/projects/{name} maps a RuntimeError to an opaque 500."""
        with patch("backend.routes.budget.ProjectBudgetService") as mock_cls:
            mock_cls.return_value = self._mock_project_service(
                update_project=RuntimeError("secret /path/to/data.db")
            )
            response = test_client_no_raise.put(
                "/api/budget/projects/Wedding", json={"total_budget": 60000.0}
            )
        assert response.status_code == 500
        assert response.json() == self.OPAQUE
