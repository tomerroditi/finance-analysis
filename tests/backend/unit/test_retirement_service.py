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
from backend.services.investments_service import InvestmentsService


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
    def test_expenses_constant_in_todays_money(self, sample_goal):
        """Expenses are constant in real terms (today's shekels) at every age."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        expected = round(sample_goal["monthly_expenses_in_retirement"] * 12, 0)
        assert all(r["expenses"] == expected for r in result)


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
        """Target age at/behind current age is not solvable — -1, not a '0' suggestion."""
        sample_goal["target_retirement_age"] = sample_goal["current_age"]
        service = RetirementService.__new__(RetirementService)
        result = service._solve_monthly_expenses(sample_goal, sample_status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_return_rate_zero_years(self, sample_goal, sample_status):
        """Target age at/behind current age is not solvable — -1, not a '0%' suggestion."""
        sample_goal["target_retirement_age"] = sample_goal["current_age"]
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(sample_goal, sample_status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solve_monthly_expenses_hopeless_returns_minus_one(
        self, sample_goal, sample_status
    ):
        """Wealth that stays negative to target yields -1, not 'spend 0'."""
        status = {
            **sample_status,
            "net_worth": -2_000_000.0,
            "monthly_savings": 0.0,
        }
        goal = {
            **sample_goal,
            "keren_hishtalmut_balance": 0.0,
            "keren_hishtalmut_monthly_contribution": 0.0,
        }
        service = RetirementService.__new__(RetirementService)
        assert service._solve_monthly_expenses(goal, status) == -1


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
    def test_readiness_off_track_when_portfolio_runs_dry(
        self, mock_status, sample_goal, sample_status
    ):
        """Off track is reserved for plans that actually run out of money."""
        sample_goal["monthly_expenses_in_retirement"] = 500000
        sample_status["net_worth"] = 1000
        sample_status["monthly_savings"] = 100
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        assert result["readiness"] == "off_track"
        assert result["fire_age"] == -1
        # Off track must be driven by depletion, not merely by missing FIRE.
        assert result["portfolio_depleted_age"] is not None

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_readiness_funded_when_solvent_without_fire(
        self, mock_status, sample_goal, sample_status
    ):
        """A plan the pension carries for life is funded, not off track.

        The FIRE number assumes the portfolio funds 100% of retirement
        spending forever — it never nets out pension / Bituach Leumi /
        passive income, even though the drawdown projection credits them.
        So a modest saver whose guaranteed income covers retirement
        spending never reaches ~28x expenses yet never runs dry either.
        That used to report off_track, which read as failure for a plan
        that always has money in it.
        """
        # Retire at the full pension age, so there is no gap for the
        # portfolio to bridge (pension / BL only start at 67). Guaranteed
        # income then exceeds spending and drawdown never touches savings.
        sample_goal["target_retirement_age"] = 67
        sample_goal["monthly_expenses_in_retirement"] = 8000.0
        sample_goal["pension_monthly_payout_estimate"] = 9000.0
        sample_goal["bituach_leumi_monthly_estimate"] = 2800.0
        sample_goal["other_passive_income"] = 0.0
        # ...but wealth stays far below the FIRE number (8000*12/0.035).
        sample_status["net_worth"] = 50000.0
        sample_status["monthly_savings"] = 100.0
        sample_goal["keren_hishtalmut_balance"] = 0.0
        sample_goal["keren_hishtalmut_monthly_contribution"] = 0.0
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)

        assert result["fire_age"] == -1
        assert result["portfolio_depleted_age"] is None
        assert result["readiness"] == "funded"

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
            "target_retirement_age", "full_pension_age",
            "net_worth_projection", "income_projection",
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

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_progress_pct_clamped_at_zero(self, mock_status, sample_goal, sample_status):
        """Negative total wealth reports 0% progress, never a negative pct.

        A negative percentage reaches the UI as an invalid negative CSS
        width, which browsers drop — rendering a visually FULL progress bar.
        """
        sample_status["net_worth"] = -500000.0
        sample_goal["keren_hishtalmut_balance"] = 0.0
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        assert result["progress_pct"] == 0.0


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


class TestCurrentStatus:
    """Tests for get_current_status averaging windows."""

    @staticmethod
    def _service(monthly_data, net_worth=0.0, total_investments=0.0):
        """Build a RetirementService with a mocked analysis_service.

        Entries are labelled with consecutive months ending at LAST month, so
        every one is a complete month. ``get_current_status`` drops the
        running month (it has partial income but near-full expenses), and
        unlabelled fixtures would not exercise that path realistically.
        """
        import pandas as pd

        service = RetirementService.__new__(RetirementService)
        analysis = MagicMock()
        last_complete = pd.Timestamp.today().normalize().replace(
            day=1
        ) - pd.DateOffset(months=1)
        labelled = [
            {
                **entry,
                "month": (
                    last_complete
                    - pd.DateOffset(months=len(monthly_data) - 1 - index)
                ).strftime("%Y-%m"),
            }
            for index, entry in enumerate(monthly_data)
        ]
        analysis.get_income_expenses_over_time.return_value = labelled
        analysis.get_net_worth_over_time.return_value = (
            [{"net_worth": net_worth}] if net_worth else []
        )
        analysis.get_overview.return_value = {
            "total_investments": total_investments
        }
        service.analysis_service = analysis
        investments = MagicMock()
        investments.get_all_investments.return_value = []
        service.investments_service = investments
        return service

    def test_expenses_use_last_12_months_income_last_6(self):
        """Expenses average the last 12 months; income the last 6."""
        # 14 months: income ramps 100..1400, expenses fixed pattern.
        monthly = [
            {"income": (i + 1) * 100, "expenses": (i + 1) * 10}
            for i in range(14)
        ]
        service = self._service(monthly)
        status = service.get_current_status()
        # Income: months 9..14 -> incomes 900..1400, mean = 1150
        assert status["avg_monthly_income"] == pytest.approx(1150.0)
        # Expenses: months 3..14 -> expenses 30..140, mean = 85
        assert status["avg_monthly_expenses"] == pytest.approx(85.0)

    def test_short_history_uses_all_available_months(self):
        """Fewer than 6 months: both averages use every month."""
        monthly = [
            {"income": 1000, "expenses": 400},
            {"income": 2000, "expenses": 600},
        ]
        service = self._service(monthly)
        status = service.get_current_status()
        assert status["avg_monthly_income"] == pytest.approx(1500.0)
        assert status["avg_monthly_expenses"] == pytest.approx(500.0)

    def test_empty_history_returns_zeros(self):
        """No monthly data yields zeroed averages without raising."""
        service = self._service([])
        status = service.get_current_status()
        assert status["avg_monthly_income"] == 0.0
        assert status["avg_monthly_expenses"] == 0.0
        assert status["monthly_savings"] == 0.0
        assert status["savings_rate"] == 0.0

    def test_tracked_kh_value_sums_hishtalmut_investments(self):
        """Status exposes the value of synced KH investments in net worth.

        get_current_status now delegates entirely to
        ``InvestmentsService.get_hishtalmut_total_balance`` (the single
        source of truth covering both scraped and manual KH investments,
        exercised directly in ``TestHishtalmutTotalBalance``), so this
        test only checks that ``get_current_status`` wires its result
        through unchanged.
        """
        service = self._service([])
        service.investments_service.get_hishtalmut_total_balance.return_value = 205000.0
        status = service.get_current_status()
        assert status["tracked_kh_value"] == 205000.0

    def test_tracked_kh_value_defaults_to_zero_when_none(self):
        """A None KH total (no KH investments) must not surface as None."""
        service = self._service([])
        service.investments_service.get_hishtalmut_total_balance.return_value = None
        status = service.get_current_status()
        assert status["tracked_kh_value"] == 0.0


class TestProjectionAlignment:
    """The projection curve is aligned to the ages it is labelled with."""

    GOAL = {
        "current_age": 40, "gender": "male", "target_retirement_age": 60,
        "life_expectancy": 85, "monthly_expenses_in_retirement": 10000,
        "inflation_rate": 0.0, "expected_return_rate": 0.05,
        "withdrawal_rate": 0.04, "pension_monthly_payout_estimate": 0,
        "keren_hishtalmut_balance": 0,
        "keren_hishtalmut_monthly_contribution": 0,
        "bituach_leumi_eligible": False, "bituach_leumi_monthly_estimate": 0,
        "other_passive_income": 0,
    }
    STATUS = {
        "net_worth": 1_000_000.0, "monthly_savings": 20_000.0,
        "avg_monthly_income": 0.0, "avg_monthly_expenses": 0.0,
        "savings_rate": 0.0, "total_investments": 0.0,
    }

    def test_first_point_is_todays_net_worth(self, db_session):
        """The point labelled current_age holds today's actual net worth.

        It used to hold a year of compounding already applied, so the chart
        opened above the user's real balance.
        """
        proj = RetirementService(db_session)._project_net_worth(
            self.GOAL, self.STATUS
        )
        assert proj[0]["age"] == 40
        assert proj[0]["net_worth_baseline"] == 1_000_000

    def test_fire_age_matches_independent_simulation(self, db_session, monkeypatch):
        """fire_age agrees with a hand-rolled simulation of the same plan."""
        status = self.STATUS
        monkeypatch.setattr(
            RetirementService, "get_current_status", lambda self: status
        )
        result = RetirementService(db_session).get_projections(
            goal_override=self.GOAL
        )
        net_worth, age = 1_000_000.0, 40
        while net_worth < 10000 * 12 / 0.04:
            net_worth = net_worth * 1.05 + 240_000.0
            age += 1
        assert result["fire_age"] == age


class TestDepletionOnlyInDrawdown:
    """A dip before retirement is not portfolio depletion."""

    def test_negative_net_worth_today_is_not_depletion(
        self, db_session, monkeypatch
    ):
        """A mortgage-driven negative net worth today is not 'off_track'.

        The scan covered the accumulation phase too, so anyone carrying
        loans was marked off_track and the solver returned 'unachievable'.
        """
        status = {**TestProjectionAlignment.STATUS, "net_worth": -500_000.0}
        monkeypatch.setattr(
            RetirementService, "get_current_status", lambda self: status
        )
        result = RetirementService(db_session).get_projections(
            goal_override=TestProjectionAlignment.GOAL
        )
        assert result["net_worth_projection"][-1]["net_worth_baseline"] > 0
        assert result["portfolio_depleted_age"] is None

    def test_solver_finds_achievable_plan(self, db_session, monkeypatch):
        """solve_all_fields does not report -1 for a plan that works."""
        status = {**TestProjectionAlignment.STATUS, "net_worth": -500_000.0}
        monkeypatch.setattr(
            RetirementService, "get_current_status", lambda self: status
        )
        solved = RetirementService(db_session).solve_all_fields(
            goal_override=TestProjectionAlignment.GOAL
        )
        assert solved["target_retirement_age"] != -1


class TestRealTermsModel:
    """The projection is computed in today's shekels with real returns."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_inflation_delays_fire_age(self, mock_status, sample_goal, sample_status):
        """Higher inflation lowers real returns, so FIRE arrives later.

        The old model compared a nominal (inflating) projection against a
        today-shekels FIRE number, so inflation had no effect on fire_age at
        all — declaring FIRE far too early.
        """
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)

        no_inflation = service.get_projections(
            goal_override={**sample_goal, "inflation_rate": 0.0}
        )
        high_inflation = service.get_projections(
            goal_override={**sample_goal, "inflation_rate": 0.03}
        )
        assert no_inflation["fire_age"] != -1
        if high_inflation["fire_age"] == -1:
            return  # never reached at all — strictly "later"
        assert high_inflation["fire_age"] > no_inflation["fire_age"]

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_manually_entered_kh_counts_on_top(self, sample_goal, sample_status):
        """A KH balance only typed into the goal adds to tracked net worth.

        With no synced KH investments (``tracked_kh_value`` 0/absent), the
        tracked net worth contains no KH, so total wealth = net worth + the
        goal's KH balance. The old code subtracted the goal KH from net
        worth unconditionally, silently dropping it for these users.
        """
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, sample_status)
        expected = sample_status["net_worth"] + sample_goal["keren_hishtalmut_balance"]
        assert result[0]["net_worth_baseline"] == round(expected, 0)

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_synced_kh_is_not_double_counted(self, sample_goal, sample_status):
        """Scraped KH auto-synced into investments is already in net worth.

        InsuranceSyncMixin creates a ``hishtalmut`` investment with scraped
        balance snapshots for every scraped policy, and the net worth series
        values investments snapshot-first — so that KH value is inside
        ``status["net_worth"]``. The projection must swap it out of the base
        portfolio before adding the goal's KH bucket, keeping the starting
        total equal to net worth (not net worth + KH again).
        """
        status = {
            **sample_status,
            "tracked_kh_value": sample_goal["keren_hishtalmut_balance"],
        }
        service = RetirementService.__new__(RetirementService)
        result = service._project_net_worth(sample_goal, status)
        assert result[0]["net_worth_baseline"] == round(status["net_worth"], 0)

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_progress_counts_keren_hishtalmut(self, mock_status, sample_goal, sample_status):
        """Progress toward the FIRE number includes the KH balance."""
        mock_status.return_value = sample_status
        service = RetirementService.__new__(RetirementService)
        result = service.get_projections(goal_override=sample_goal)
        fire_number = sample_goal["monthly_expenses_in_retirement"] * 12 / sample_goal["withdrawal_rate"]
        expected = (
            (sample_status["net_worth"] + sample_goal["keren_hishtalmut_balance"])
            / fire_number * 100
        )
        assert result["progress_pct"] == pytest.approx(expected, abs=0.11)


class TestSolverTargetsOnTrack:
    """Solvers must target readiness (FIRE by target + survival), not survival alone."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_return_rate_not_fooled_by_pension_covered_plan(self, sample_goal, sample_status):
        """A plan whose pension covers all expenses survives at ANY rate.

        The old survival-only binary search converged to its lower bound and
        suggested a nonsensical ~-10% return while the plan stayed off-track
        (FIRE number never reached). It must return -1 instead.
        """
        goal = {
            **sample_goal,
            "monthly_expenses_in_retirement": 10000.0,
            "other_passive_income": 12000.0,  # covers expenses at every age
            "target_retirement_age": 50,
        }
        status = {**sample_status, "net_worth": 1000.0, "monthly_savings": 100.0}
        goal["keren_hishtalmut_balance"] = 0.0
        goal["keren_hishtalmut_monthly_contribution"] = 0.0
        service = RetirementService.__new__(RetirementService)
        result = service._solve_return_rate(goal, status)
        assert result == -1

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solved_return_rate_puts_plan_on_track(self, sample_goal, sample_status):
        """Applying the solved rate must actually make the plan on track."""
        service = RetirementService.__new__(RetirementService)
        rate = service._solve_return_rate(sample_goal, sample_status)
        if rate == -1:
            return
        assert service._plan_on_track(
            {**sample_goal, "expected_return_rate": rate}, sample_status
        )

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_solved_expenses_put_plan_on_track(self, sample_goal, sample_status):
        """Applying the solved retirement expenses must make the plan on track."""
        service = RetirementService.__new__(RetirementService)
        expenses = service._solve_monthly_expenses(sample_goal, sample_status)
        assert expenses > 0
        assert service._plan_on_track(
            {**sample_goal, "monthly_expenses_in_retirement": expenses}, sample_status
        )

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_life_expectancy_not_suggested_when_fire_unreachable(
        self, sample_goal, sample_status
    ):
        """Shorter life expectancy can't fix a plan that never reaches FIRE."""
        goal = {
            **sample_goal,
            "monthly_expenses_in_retirement": 100000.0,
            "other_passive_income": 150000.0,  # survives forever
        }
        status = {**sample_status, "net_worth": 1000.0, "monthly_savings": 100.0}
        service = RetirementService.__new__(RetirementService)
        assert service._solve_life_expectancy(goal, status) == -1


class TestSolversRespectOverrides:
    """solve_all_fields must use the same override-adjusted status as projections."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    @patch.object(RetirementService, "get_current_status")
    def test_income_override_changes_suggestions(
        self, mock_status, sample_goal, sample_status
    ):
        """A monthly income override must flow into the solved target age."""
        mock_status.return_value = {
            **sample_status,
            "avg_monthly_income": 13000.0,
            "avg_monthly_expenses": 12000.0,
            "monthly_savings": 1000.0,
        }
        service = RetirementService.__new__(RetirementService)

        base = service.solve_all_fields(goal_override=sample_goal)
        boosted = service.solve_all_fields(
            goal_override={**sample_goal, "monthly_income": 40000.0}
        )
        # 28k/mo savings instead of 1k must allow retiring earlier (or make
        # an unreachable plan reachable).
        if base["target_retirement_age"] == -1:
            assert boosted["target_retirement_age"] != -1
        else:
            assert (
                boosted["target_retirement_age"] < base["target_retirement_age"]
            )


class TestAdditionalSavingsSemantics:
    """monthly_savings_needed is the EXTRA saving beyond current contributions."""

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_on_track_plan_needs_zero_extra(self, sample_goal, sample_status):
        """A plan already reaching FIRE by target age reports 0 extra needed.

        The old formula returned the TOTAL required monthly saving, so users
        who were already saving enough still saw a large amber number.
        """
        service = RetirementService.__new__(RetirementService)
        # Make the plan comfortably on track via wealth
        status = {**sample_status, "net_worth": 4500000.0}
        fire_number = (
            sample_goal["monthly_expenses_in_retirement"] * 12
            / sample_goal["withdrawal_rate"]
        )
        assert service._calc_required_monthly_savings(
            sample_goal, status, fire_number
        ) == 0.0

    @patch.object(RetirementService, "__init__", lambda self, db: None)
    def test_extra_savings_close_the_gap_exactly(self, sample_goal, sample_status):
        """Saving current + extra reaches the FIRE number at the target age."""
        from backend.services.retirement_service import _real_rate

        service = RetirementService.__new__(RetirementService)
        status = {**sample_status, "net_worth": 500000.0}
        fire_number = (
            sample_goal["monthly_expenses_in_retirement"] * 12
            / sample_goal["withdrawal_rate"]
        )
        extra = service._calc_required_monthly_savings(
            sample_goal, status, fire_number
        )
        assert extra > 0

        # Re-simulate the accumulation with the extra savings applied
        rate = _real_rate(
            sample_goal["expected_return_rate"], sample_goal["inflation_rate"]
        )
        years = sample_goal["target_retirement_age"] - sample_goal["current_age"]
        wealth = status["net_worth"] + sample_goal["keren_hishtalmut_balance"]
        annual = (
            status["monthly_savings"]
            + sample_goal["keren_hishtalmut_monthly_contribution"]
            + extra
        ) * 12
        for _ in range(years):
            wealth = wealth * (1 + rate) + annual
        assert wealth == pytest.approx(fire_number, rel=1e-6)


class TestStatusExcludesPartialMonth:
    """Averages must not be diluted by the running month."""

    def test_avg_income_ignores_current_month(self, db_session):
        """Six complete 10k-salary months average to 10k, not 8.3k."""
        import pandas as pd
        from backend.models.transaction import BankTransaction

        today = pd.Timestamp.today().normalize()
        rows, i = [], 0
        for k in range(1, 7):
            month = (today - pd.DateOffset(months=k)).replace(day=10)
            for amount, category in ((10000.0, "Salary"), (-4000.0, "Food")):
                rows.append(
                    BankTransaction(
                        id=f"pm{i}", date=month.strftime("%Y-%m-%d"),
                        provider="p", account_name="a", description="d",
                        amount=amount, category=category, tag=None,
                        source="bank_transactions", type="normal",
                        status="completed",
                    )
                )
                i += 1
        rows.append(
            BankTransaction(
                id=f"pm{i}", date=today.replace(day=1).strftime("%Y-%m-%d"),
                provider="p", account_name="a", description="partial",
                amount=-100.0, category="Food", tag=None,
                source="bank_transactions", type="normal", status="completed",
            )
        )
        db_session.add_all(rows)
        db_session.commit()

        status = RetirementService(db_session).get_current_status()
        assert status["avg_monthly_income"] == 10000.0
        assert status["monthly_savings"] == 6000.0


class TestKerenHishtalmutSingleCount:
    """The KH swap must net to zero for scraped and manual KH alike."""

    def test_tracked_value_matches_suggested_bucket(self, db_session):
        """Verify tracked_kh_value equals the suggested KH balance default.

        get_current_status subtracts tracked_kh_value from the base
        portfolio and the projection adds the KH bucket back. If the two
        are computed from different sources, a manually-created KH
        investment is subtracted and never re-added.
        """
        investments = InvestmentsService(db_session)
        scraped_id = investments.investments_repo.create_investment(
            category="Investments",
            tag="Keren Hishtalmut - hafenix (007-916-407357)",
            type_="hishtalmut",
            name="Scraped KH",
            insurance_policy_id="007-916-407357",
        )
        manual_id = investments.investments_repo.create_investment(
            category="Investments",
            tag="Keren Hishtalmut - manual",
            type_="hishtalmut",
            name="Manual KH",
        )
        investments.create_balance_snapshot(scraped_id, "2026-08-30", 56957.0)
        investments.create_balance_snapshot(manual_id, "2026-08-30", 12000.0)

        service = RetirementService(db_session)
        tracked = service.get_current_status()["tracked_kh_value"]
        suggested = service.get_scraped_defaults()["keren_hishtalmut_balance"]

        assert tracked == pytest.approx(68957.0)
        assert suggested == pytest.approx(tracked)
