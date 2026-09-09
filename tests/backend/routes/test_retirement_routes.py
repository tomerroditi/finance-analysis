"""Tests for the /api/retirement API endpoints.

The route layer is thin, so these tests focus on the HTTP contract:
response shapes, validation rejections, the null-goal cases, and the
error mapping for solver requests. Heavy projection math is covered in
``tests/backend/unit/test_retirement_service.py``.
"""

from unittest.mock import patch

import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.retirement_goal import RetirementGoal

GOAL_BODY = {
    "current_age": 35,
    "gender": "female",
    "target_retirement_age": 55,
    "life_expectancy": 90,
    "monthly_expenses_in_retirement": 12000.0,
    "inflation_rate": 0.02,
    "expected_return_rate": 0.05,
    "withdrawal_rate": 0.035,
    "pension_monthly_payout_estimate": 4000.0,
    "keren_hishtalmut_balance": 150000.0,
    "keren_hishtalmut_monthly_contribution": 1500.0,
    "bituach_leumi_eligible": True,
    "bituach_leumi_monthly_estimate": 2800.0,
    "other_passive_income": 500.0,
}


@pytest.fixture
def saved_goal(db_session):
    """Persist a retirement goal directly through the ORM."""
    goal = RetirementGoal(**GOAL_BODY)
    db_session.add(goal)
    db_session.commit()
    return goal


class TestGoalEndpoints:
    """GET / PUT /api/retirement/goal."""

    def test_get_goal_returns_null_when_unconfigured(self, test_client):
        """An unconfigured profile is ``null``, not a 404."""
        response = test_client.get("/api/retirement/goal")
        assert response.status_code == 200
        assert response.json() is None

    def test_get_goal_returns_saved_profile(self, test_client, saved_goal):
        """The saved profile round-trips with booleans coerced from SQLite ints."""
        response = test_client.get("/api/retirement/goal")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == saved_goal.id
        assert data["gender"] == "female"
        assert data["bituach_leumi_eligible"] is True
        assert data["net_worth_override"] is None

    def test_put_goal_creates_then_updates_in_place(self, test_client):
        """Two PUTs produce one row; the second overwrites the first."""
        first = test_client.put("/api/retirement/goal", json=GOAL_BODY)
        assert first.status_code == 200
        first_id = first.json()["id"]

        second = test_client.put(
            "/api/retirement/goal",
            json={**GOAL_BODY, "target_retirement_age": 60, "net_worth_override": 1_000_000},
        )
        assert second.status_code == 200
        assert second.json()["id"] == first_id
        assert second.json()["target_retirement_age"] == 60
        assert second.json()["net_worth_override"] == 1_000_000

    @pytest.mark.parametrize(
        "override",
        [
            {"current_age": 17},
            {"gender": "other"},
            {"monthly_expenses_in_retirement": 0},
            {"withdrawal_rate": 0},
            {"withdrawal_rate": 0.5},
            {"inflation_rate": -0.01},
            {"expected_return_rate": 0.5},
            {"life_expectancy": 130},
            {"net_worth_override": -1},
        ],
    )
    def test_put_goal_rejects_out_of_range_fields(self, test_client, override):
        """Pydantic bounds reject implausible inputs with 422."""
        response = test_client.put("/api/retirement/goal", json={**GOAL_BODY, **override})
        assert response.status_code == 422

    def test_put_goal_requires_mandatory_fields(self, test_client):
        """Omitting a required field is a 422."""
        body = {k: v for k, v in GOAL_BODY.items() if k != "monthly_expenses_in_retirement"}
        assert test_client.put("/api/retirement/goal", json=body).status_code == 422


class TestStatusAndProjections:
    """Computed endpoints that run the real service against an empty DB."""

    def test_status_on_empty_db_is_all_zeros(self, test_client):
        """With no tracked data every status figure is zero but the shape is complete."""
        response = test_client.get("/api/retirement/status")
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {
            "net_worth",
            "avg_monthly_expenses",
            "avg_monthly_income",
            "savings_rate",
            "total_investments",
            "monthly_savings",
        }
        assert all(v == 0 for v in data.values())

    def test_get_projections_without_goal_is_404(self, test_client):
        """Saved-goal projections need a saved goal."""
        response = test_client.get("/api/retirement/projections")
        assert response.status_code == 404

    def test_get_projections_with_goal(self, test_client, saved_goal):
        """A saved goal produces a full projection payload."""
        response = test_client.get("/api/retirement/projections")
        assert response.status_code == 200
        data = response.json()
        assert data["target_retirement_age"] == 55
        assert data["full_pension_age"] == 65
        assert data["readiness"] in {"on_track", "close", "off_track", "funded"}
        assert data["net_worth_projection"][0]["age"] == 35
        assert data["net_worth_projection"][-1]["age"] == 90
        assert len(data["income_projection"]) == len(data["net_worth_projection"])

    def test_preview_projections_does_not_persist(self, test_client):
        """POST /projections computes from the body and leaves the goal unset."""
        response = test_client.post("/api/retirement/projections", json=GOAL_BODY)
        assert response.status_code == 200
        assert response.json()["target_retirement_age"] == 55
        assert test_client.get("/api/retirement/goal").json() is None

    def test_preview_projections_validates_body(self, test_client):
        """The preview body is validated like the save body."""
        response = test_client.post(
            "/api/retirement/projections", json={**GOAL_BODY, "current_age": 5}
        )
        assert response.status_code == 422


class TestSuggestions:
    """Auto-adjust solver endpoints."""

    def test_get_suggestions_without_goal_is_404(self, test_client):
        """Suggestions for a saved goal need a saved goal."""
        assert test_client.get("/api/retirement/suggestions").status_code == 404

    def test_get_suggestions_with_goal(self, test_client, saved_goal):
        """All four adjustable fields are solved."""
        response = test_client.get("/api/retirement/suggestions")
        assert response.status_code == 200
        assert set(response.json()) == {
            "target_retirement_age",
            "monthly_expenses_in_retirement",
            "expected_return_rate",
            "life_expectancy",
        }

    def test_preview_suggestions_uses_body(self, test_client):
        """POST /suggestions solves from the body without a saved goal."""
        response = test_client.post("/api/retirement/suggestions", json=GOAL_BODY)
        assert response.status_code == 200
        assert isinstance(response.json()["target_retirement_age"], int)

    @pytest.mark.parametrize(
        "field, unit",
        [
            ("target_retirement_age", "age"),
            ("monthly_expenses_in_retirement", "currency"),
            ("expected_return_rate", "rate"),
            ("life_expectancy", "age"),
        ],
    )
    def test_solve_each_supported_field(self, test_client, saved_goal, field, unit):
        """Every supported field reports its own unit."""
        response = test_client.get(f"/api/retirement/solve/{field}")
        assert response.status_code == 200
        data = response.json()
        assert data["field"] == field
        assert data["unit"] == unit
        assert isinstance(data["value"], (int, float))

    def test_solve_unknown_field_is_400(self, test_client, saved_goal):
        """A field the solver does not support is a validation error."""
        response = test_client.get("/api/retirement/solve/withdrawal_rate")
        assert response.status_code == 400

    def test_solve_without_goal_is_404(self, test_client):
        """Solving needs a configured goal."""
        response = test_client.get("/api/retirement/solve/target_retirement_age")
        assert response.status_code == 404

    def test_service_exceptions_map_to_status_codes(self, test_client):
        """Domain exceptions raised by the service surface as 404 / 400."""
        with patch("backend.routes.retirement.RetirementService") as mock:
            mock.return_value.solve_for_field.side_effect = EntityNotFoundException("no goal")
            assert test_client.get("/api/retirement/solve/x").status_code == 404
            mock.return_value.solve_for_field.side_effect = ValidationException("bad field")
            assert test_client.get("/api/retirement/solve/x").status_code == 400


class TestScrapedDefaults:
    """Auto-fill helpers backed by scraped insurance data."""

    def test_keren_hishtalmut_balance_is_null_without_data(self, test_client):
        """No KH investments means a null balance, not zero."""
        response = test_client.get("/api/retirement/keren-hishtalmut-balance")
        assert response.status_code == 200
        assert response.json() == {"balance": None}

    def test_scraped_defaults_are_all_null_without_data(self, test_client):
        """Every auto-fill value is null on an empty database."""
        response = test_client.get("/api/retirement/scraped-defaults")
        assert response.status_code == 200
        assert response.json() == {
            "keren_hishtalmut_balance": None,
            "keren_hishtalmut_monthly_contribution": None,
            "pension_monthly_deposit": None,
            "avg_monthly_salary": None,
        }

    def test_scraped_defaults_include_salary_average(self, test_client, seed_base_transactions):
        """Salary transactions feed the average-salary default."""
        response = test_client.get("/api/retirement/scraped-defaults")
        assert response.status_code == 200
        assert response.json()["avg_monthly_salary"] == pytest.approx((8000 + 8500 + 8200) / 3)
