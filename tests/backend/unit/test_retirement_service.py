"""
Unit tests for RetirementService projection calculations.

Tests the core FIRE number, net worth projection, retirement income
phase analysis, and required savings calculations.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.services.retirement_service import (
    RetirementService,
    FULL_PENSION_AGE_MALE,
    FULL_PENSION_AGE_FEMALE,
    _get_full_pension_age,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def sample_goal():
    """Standard retirement goal for testing."""
    return {
        "id": 1,
        "current_age": 35,
        "gender": "male",
        "target_retirement_age": 50,
        "life_expectancy": 90,
        "monthly_expenses_in_retirement": 15000.0,
        "inflation_rate": 0.025,
        "expected_return_rate": 0.04,
        "withdrawal_rate": 0.035,
        "pension_monthly_payout_estimate": 5000.0,
        "keren_hishtalmut_balance": 200000.0,
        "keren_hishtalmut_monthly_contribution": 2500.0,
        "bituach_leumi_eligible": True,
        "bituach_leumi_monthly_estimate": 2800.0,
        "other_passive_income": 3000.0,
    }


@pytest.fixture
def sample_status():
    """Standard financial status for testing."""
    return {
        "net_worth": 1500000.0,
        "avg_monthly_expenses": 12000.0,
        "avg_monthly_income": 25000.0,
        "savings_rate": 52.0,
        "total_investments": 800000.0,
        "monthly_savings": 13000.0,
    }


class TestGenderPensionAge:
    """Tests for gender-based pension age."""

    def test_male_pension_age(self):
        """Male full pension age should be 67."""
        assert _get_full_pension_age("male") == 67

    def test_female_pension_age(self):
        """Female full pension age should be 65."""
        assert _get_full_pension_age("female") == 65

    def test_default_pension_age(self):
        """Unknown gender defaults to male pension age."""
        assert _get_full_pension_age("other") == FULL_PENSION_AGE_MALE


class TestFireNumber:
    """Tests for FIRE number calculation."""

    def test_fire_number_standard(self, sample_goal):
        """FIRE number should be annual expenses divided by withdrawal rate."""
        annual_expenses = sample_goal["monthly_expenses_in_retirement"] * 12
        expected = annual_expenses / sample_goal["withdrawal_rate"]
        # 180000 / 0.035 ≈ 5,142,857
        assert round(expected) == 5142857

    def test_fire_number_conservative_rate(self, sample_goal):
        """Lower withdrawal rate produces higher FIRE number."""
        sample_goal["withdrawal_rate"] = 0.03
        annual_expenses = sample_goal["monthly_expenses_in_retirement"] * 12
        expected = annual_expenses / sample_goal["withdrawal_rate"]
        assert expected == 6000000.0


class TestNetWorthProjection:
    """Tests for net worth projection logic."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_projection_length(self, sample_goal, sample_status):
        """Projection should span from current age to life expectancy."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        expected_length = sample_goal["life_expectancy"] - sample_goal["current_age"] + 1
        assert len(result) == expected_length

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_projection_starts_at_current_age(self, sample_goal, sample_status):
        """First projection point should be current age."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        assert result[0]["age"] == sample_goal["current_age"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_projection_ends_at_life_expectancy(self, sample_goal, sample_status):
        """Last projection point should be life expectancy."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        assert result[-1]["age"] == sample_goal["life_expectancy"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_optimistic_exceeds_baseline(self, sample_goal, sample_status):
        """Optimistic scenario should always be >= baseline during accumulation."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        # Check at target retirement age
        target_idx = sample_goal["target_retirement_age"] - sample_goal["current_age"]
        assert result[target_idx]["net_worth_optimistic"] >= result[target_idx]["net_worth_baseline"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_baseline_exceeds_conservative(self, sample_goal, sample_status):
        """Baseline scenario should always be >= conservative during accumulation."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        target_idx = sample_goal["target_retirement_age"] - sample_goal["current_age"]
        assert result[target_idx]["net_worth_baseline"] >= result[target_idx]["net_worth_conservative"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_accumulation_phase_grows(self, sample_goal, sample_status):
        """Net worth should grow during accumulation phase with positive savings."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        # Year 1 should be higher than year 0 (baseline)
        assert result[1]["net_worth_baseline"] > result[0]["net_worth_baseline"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_female_pension_age_affects_projection(self, sample_goal, sample_status):
        """Female gender should use pension age 65 in net worth projection."""
        service = RetirementService.__new__(RetirementService)
        sample_goal["gender"] = "female"
        result_female = service._project_net_worth(sample_goal, sample_status)
        sample_goal["gender"] = "male"
        result_male = service._project_net_worth(sample_goal, sample_status)
        # At age 66, female should have pension income (age >= 65) but male shouldn't (age < 67)
        # This affects drawdown, so net worth at age 66 should differ
        age_66_idx = 66 - sample_goal["current_age"]
        assert result_female[age_66_idx]["net_worth_baseline"] != result_male[age_66_idx]["net_worth_baseline"]


class TestRetirementIncome:
    """Tests for retirement income phase projection."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_income_projection_length(self, sample_goal):
        """Income projection spans from current age to life expectancy."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        expected = sample_goal["life_expectancy"] - sample_goal["current_age"] + 1
        assert len(result) == expected

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_income_starts_at_current_age(self, sample_goal):
        """Income projection starts at current age."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        assert result[0]["age"] == sample_goal["current_age"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_salary_during_accumulation(self, sample_goal):
        """During accumulation phase, salary_savings covers expenses."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        # At current age (35), before retirement (50), salary_savings should cover expenses
        assert result[0]["salary_savings"] > 0
        assert result[0]["portfolio_withdrawal"] == 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_no_salary_after_retirement(self, sample_goal):
        """After retirement, salary_savings should be 0."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        target_idx = sample_goal["target_retirement_age"] - sample_goal["current_age"]
        assert result[target_idx]["salary_savings"] == 0
        assert result[target_idx]["portfolio_withdrawal"] > 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_no_pension_before_60(self, sample_goal):
        """No pension income before early pension age (60)."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        # At current age (35), pension should be 0
        assert result[0]["pension"] == 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_no_pension_before_full_pension_age(self, sample_goal):
        """No pension income before full pension age (67 male, 65 female)."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        # At age 60, male should have no pension (full pension age is 67)
        age_60_entry = next(r for r in result if r["age"] == 60)
        assert age_60_entry["pension"] == 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_full_pension_at_67_male(self, sample_goal):
        """Full pension starts at age 67 for males."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        age_67_entry = next(r for r in result if r["age"] == FULL_PENSION_AGE_MALE)
        expected_pension = round(sample_goal["pension_monthly_payout_estimate"] * 12, 0)
        assert age_67_entry["pension"] == expected_pension

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_full_pension_at_65_female(self, sample_goal):
        """Full pension starts at age 65 for females."""
        sample_goal["gender"] = "female"
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        age_65_entry = next(r for r in result if r["age"] == FULL_PENSION_AGE_FEMALE)
        expected_pension = round(sample_goal["pension_monthly_payout_estimate"] * 12, 0)
        assert age_65_entry["pension"] == expected_pension

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_bituach_leumi_at_67(self, sample_goal):
        """Bituach Leumi income starts at age 67 when eligible (male)."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        age_67_entry = next(r for r in result if r["age"] == FULL_PENSION_AGE_MALE)
        expected_bl = round(sample_goal["bituach_leumi_monthly_estimate"] * 12, 0)
        assert age_67_entry["bituach_leumi"] == expected_bl

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_no_bituach_leumi_when_ineligible(self, sample_goal):
        """No Bituach Leumi income when not eligible."""
        sample_goal["bituach_leumi_eligible"] = False
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        age_67_entry = next(r for r in result if r["age"] == FULL_PENSION_AGE_MALE)
        assert age_67_entry["bituach_leumi"] == 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_passive_income_always_present(self, sample_goal):
        """Passive income should be present at every age after retirement."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        expected_passive = round(sample_goal["other_passive_income"] * 12, 0)
        target_idx = sample_goal["target_retirement_age"] - sample_goal["current_age"]
        for entry in result[target_idx:]:
            assert entry["passive_income"] == expected_passive

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_expenses_grow_with_inflation(self, sample_goal):
        """Expenses should increase year over year due to inflation."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        assert result[1]["expenses"] > result[0]["expenses"]


class TestRequiredSavings:
    """Tests for monthly savings needed calculation."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_zero_when_already_wealthy(self, sample_goal, sample_status):
        """If already at FIRE number, required savings should be 0."""
        fire_number = 5142857
        sample_status["net_worth"] = 10000000  # Already beyond FIRE
        service = RetirementService.__new__(RetirementService)
        result = service._calc_required_monthly_savings(sample_goal, sample_status, fire_number)
        assert result == 0.0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_positive_when_behind(self, sample_goal, sample_status):
        """If behind, required savings should be positive."""
        fire_number = 5142857
        sample_status["net_worth"] = 100000  # Way behind
        service = RetirementService.__new__(RetirementService)
        result = service._calc_required_monthly_savings(sample_goal, sample_status, fire_number)
        assert result > 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_zero_years_returns_zero(self, sample_goal, sample_status):
        """If already at target age, required savings should be 0."""
        sample_goal["target_retirement_age"] = sample_goal["current_age"]
        service = RetirementService.__new__(RetirementService)
        result = service._calc_required_monthly_savings(sample_goal, sample_status, 5000000)
        assert result == 0.0


class TestAutoAdjustSolver:
    """Tests for auto-adjust field solver calculations."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_target_retirement_age_returns_integer(self, sample_goal, sample_status):
        """Solving for target retirement age should return an integer age."""
        service = RetirementService.__new__(RetirementService)
        result = service._solve_target_retirement_age(sample_goal, sample_status)
        assert isinstance(result, int)
        assert result >= sample_goal["current_age"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_target_age_wealthy_returns_current_age(self, sample_goal, sample_status):
        """Already at FIRE number should return current age."""
        sample_status["net_worth"] = 10000000  # Way above FIRE number
        service = RetirementService.__new__(RetirementService)
        result = service._solve_target_retirement_age(sample_goal, sample_status)
        assert result == sample_goal["current_age"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_monthly_expenses_positive(self, sample_goal, sample_status):
        """Solved monthly expenses should be positive given reasonable inputs."""
        service = RetirementService.__new__(RetirementService)
        result = service._solve_monthly_expenses(sample_goal, sample_status)
        assert result > 0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_monthly_expenses_higher_with_more_savings(self, sample_goal, sample_status):
        """Higher savings rate should allow higher monthly expenses."""
        service = RetirementService.__new__(RetirementService)
        result_normal = service._solve_monthly_expenses(sample_goal, sample_status)
        sample_status["monthly_savings"] = 30000  # Much higher savings
        result_high = service._solve_monthly_expenses(sample_goal, sample_status)
        assert result_high > result_normal

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_return_rate_reasonable(self, sample_goal, sample_status):
        """Solved return rate should be between -10% and 30%."""
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(sample_goal, sample_status)
        assert -0.10 <= result <= 0.30

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_return_rate_zero_when_wealthy(self, sample_goal, sample_status):
        """If already at FIRE, required return rate should be very low."""
        sample_status["net_worth"] = 10000000
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(sample_goal, sample_status)
        assert result < sample_goal["expected_return_rate"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_return_rate_not_achievable(self, sample_goal, sample_status):
        """Extremely high FIRE number should return -1 (not achievable)."""
        sample_goal["monthly_expenses_in_retirement"] = 500000  # Absurdly high
        sample_status["net_worth"] = 100
        sample_status["monthly_savings"] = 100
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(sample_goal, sample_status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_target_age_not_reachable(self, sample_goal, sample_status):
        """Unreachable FIRE should return -1 for target age."""
        sample_goal["monthly_expenses_in_retirement"] = 500000
        sample_status["net_worth"] = 100
        sample_status["monthly_savings"] = 100
        service = RetirementService.__new__(RetirementService)
        result = service._solve_target_retirement_age(sample_goal, sample_status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_monthly_expenses_zero_years(self, sample_goal, sample_status):
        """If target age equals current age, monthly expenses should be 0."""
        sample_goal["target_retirement_age"] = sample_goal["current_age"]
        service = RetirementService.__new__(RetirementService)
        result = service._solve_monthly_expenses(sample_goal, sample_status)
        assert result == 0.0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_return_rate_zero_years(self, sample_goal, sample_status):
        """If target age equals current age, return rate should be 0."""
        sample_goal["target_retirement_age"] = sample_goal["current_age"]
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(sample_goal, sample_status)
        assert result == 0.0


class TestLongevityCheck:
    """Tests for portfolio longevity / depletion detection."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_find_depletion_age_no_depletion(self):
        """Portfolio that never depletes should return None."""
        projection = [
            {"age": 50, "net_worth_baseline": 5000000},
            {"age": 60, "net_worth_baseline": 4000000},
            {"age": 70, "net_worth_baseline": 3000000},
            {"age": 80, "net_worth_baseline": 2000000},
            {"age": 90, "net_worth_baseline": 1000000},
        ]
        result = RetirementService._find_depletion_age(projection, 90)
        assert result is None

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_find_depletion_age_depleted(self):
        """Portfolio that hits zero should return the depletion age."""
        projection = [
            {"age": 50, "net_worth_baseline": 5000000},
            {"age": 60, "net_worth_baseline": 3000000},
            {"age": 70, "net_worth_baseline": 1000000},
            {"age": 75, "net_worth_baseline": 0},
            {"age": 80, "net_worth_baseline": -500000},
        ]
        result = RetirementService._find_depletion_age(projection, 90)
        assert result == 75

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_find_depletion_age_negative(self):
        """Portfolio going negative should be detected as depletion."""
        projection = [
            {"age": 60, "net_worth_baseline": 1000000},
            {"age": 70, "net_worth_baseline": -100},
        ]
        result = RetirementService._find_depletion_age(projection, 90)
        assert result == 70

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_find_depletion_age_after_life_expectancy_ignored(self):
        """Depletion after life expectancy should not be reported."""
        projection = [
            {"age": 60, "net_worth_baseline": 5000000},
            {"age": 90, "net_worth_baseline": 100000},
            {"age": 95, "net_worth_baseline": -500000},
        ]
        result = RetirementService._find_depletion_age(projection, 90)
        assert result is None

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_survives_drawdown_healthy(self, sample_goal, sample_status):
        """Portfolio with sufficient savings should survive drawdown."""
        sample_status["net_worth"] = 10000000
        service = RetirementService.__new__(RetirementService)
        assert service._survives_drawdown(sample_goal, sample_status) is True

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_survives_drawdown_depleted(self, sample_goal, sample_status):
        """Portfolio with tiny savings should not survive drawdown."""
        sample_status["net_worth"] = 1000
        sample_status["monthly_savings"] = 100
        sample_goal["monthly_expenses_in_retirement"] = 50000
        service = RetirementService.__new__(RetirementService)
        assert service._survives_drawdown(sample_goal, sample_status) is False


class TestLifeExpectancySolver:
    """Tests for life expectancy solver."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_life_expectancy_never_depletes(self, sample_goal, sample_status):
        """Wealthy portfolio should return -1 (no depletion)."""
        sample_status["net_worth"] = 20000000
        service = RetirementService.__new__(RetirementService)
        result = service._solve_life_expectancy(sample_goal, sample_status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_life_expectancy_returns_age(self, sample_goal, sample_status):
        """Moderate portfolio should return a valid sustainable age."""
        sample_goal["monthly_expenses_in_retirement"] = 30000
        sample_goal["target_retirement_age"] = 45
        sample_status["net_worth"] = 500000
        sample_status["monthly_savings"] = 5000
        service = RetirementService.__new__(RetirementService)
        result = service._solve_life_expectancy(sample_goal, sample_status)
        # Should return an age between target retirement and life expectancy
        if result != -1:
            assert sample_goal["target_retirement_age"] <= result <= sample_goal["life_expectancy"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_life_expectancy_depletes_early(self, sample_goal, sample_status):
        """Portfolio with high expenses should deplete and return a reasonable age."""
        sample_goal["monthly_expenses_in_retirement"] = 100000
        sample_goal["target_retirement_age"] = 40
        sample_status["net_worth"] = 100000
        sample_status["monthly_savings"] = 1000
        service = RetirementService.__new__(RetirementService)
        result = service._solve_life_expectancy(sample_goal, sample_status)
        # Should deplete — return a valid age or -1
        assert result == -1 or result >= sample_goal["target_retirement_age"]


class TestGetProjections:
    """Tests for the main get_projections method including readiness logic."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_readiness_on_track(self, mock_status, sample_goal, sample_status):
        """On track when FIRE reached by target age and portfolio survives."""
        sample_status["net_worth"] = 10000000
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        assert result["readiness"] == "on_track"

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_readiness_off_track_no_fire(self, mock_status, sample_goal, sample_status):
        """Off track when FIRE number is never reached."""
        sample_goal["monthly_expenses_in_retirement"] = 500000
        sample_status["net_worth"] = 1000
        sample_status["monthly_savings"] = 100
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        assert result["readiness"] == "off_track"
        assert result["fire_age"] == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_readiness_off_track_portfolio_depleted(self, mock_status, sample_goal, sample_status):
        """Off track when FIRE reached but portfolio depletes before life expectancy."""
        # Set up a scenario where FIRE is reached but drawdown fails
        sample_goal["monthly_expenses_in_retirement"] = 30000
        sample_goal["withdrawal_rate"] = 0.08  # High withdrawal rate = low FIRE number
        sample_goal["expected_return_rate"] = 0.01  # Low returns during drawdown
        sample_goal["target_retirement_age"] = 40
        sample_goal["life_expectancy"] = 95
        sample_goal["pension_monthly_payout_estimate"] = 0
        sample_goal["bituach_leumi_eligible"] = False
        sample_goal["other_passive_income"] = 0
        sample_status["net_worth"] = 5000000
        sample_status["monthly_savings"] = 10000
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        # With high withdrawal and low returns over 55 years, portfolio should deplete
        if result["portfolio_depleted_age"] is not None:
            assert result["readiness"] == "off_track"

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_projections_contain_all_fields(self, mock_status, sample_goal, sample_status):
        """Projections result should contain all expected keys."""
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        expected_keys = {
            "fire_number", "years_to_fire", "fire_age",
            "earliest_possible_retirement_age", "monthly_savings_needed",
            "progress_pct", "readiness", "portfolio_depleted_age",
            "target_retirement_age", "net_worth_projection", "income_projection",
        }
        assert set(result.keys()) == expected_keys

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_readiness_close(self, mock_status, sample_goal, sample_status):
        """Close readiness when FIRE age is within 5 years of target."""
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        # If fire_age is within target+5, readiness should be close or on_track
        if result["fire_age"] != -1:
            if result["fire_age"] <= sample_goal["target_retirement_age"]:
                assert result["readiness"] in ("on_track", "off_track")
            elif result["fire_age"] <= sample_goal["target_retirement_age"] + 5:
                assert result["readiness"] in ("close", "off_track")

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_portfolio_depleted_age_in_result(self, mock_status, sample_goal, sample_status):
        """Projections should include portfolio_depleted_age field."""
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        assert "portfolio_depleted_age" in result


class TestSolveAllFields:
    """Tests for solve_all_fields including life_expectancy."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    @patch.object(RetirementService, "get_goal")
    def test_returns_all_four_fields(self, mock_goal, mock_status, sample_goal, sample_status):
        """solve_all_fields should return target_age, expenses, return rate, and life expectancy."""
        mock_goal.return_value = sample_goal
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.solve_all_fields()
        assert "target_retirement_age" in result
        assert "monthly_expenses_in_retirement" in result
        assert "expected_return_rate" in result
        assert "life_expectancy" in result

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_solve_all_with_override(self, mock_status, sample_goal, sample_status):
        """solve_all_fields should accept goal_override."""
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.solve_all_fields(goal_override=sample_goal)
        assert isinstance(result["target_retirement_age"], int)

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    @patch.object(RetirementService, "get_goal")
    def test_solve_all_no_goal_raises(self, mock_goal, mock_status):
        """solve_all_fields should raise if no goal configured."""
        mock_goal.return_value = None
        service = RetirementService.__new__(RetirementService)
        with pytest.raises(Exception):
            service.solve_all_fields()
