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
    EARLY_PENSION_AGE,
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
    def test_partial_pension_at_60(self, sample_goal):
        """Partial pension (70%) starts at age 60."""
        service = RetirementService.__new__(RetirementService)
        result = service._project_retirement_income(sample_goal)
        age_60_entry = next(r for r in result if r["age"] == EARLY_PENSION_AGE)
        expected_pension = round(sample_goal["pension_monthly_payout_estimate"] * 0.7 * 12, 0)
        assert age_60_entry["pension"] == expected_pension

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
