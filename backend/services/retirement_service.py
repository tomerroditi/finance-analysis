"""
Retirement planning business logic.

Computes FIRE projections, net worth trajectories, and retirement income
phase analysis for the Israeli financial context.
"""

from sqlalchemy.orm import Session

from backend.repositories.retirement_goal_repository import RetirementGoalRepository
from backend.services.insurance_account_service import InsuranceAccountService
from backend.services.analysis_service import AnalysisService
from backend.services.investments_service import InvestmentsService
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService
from backend.errors import EntityNotFoundException, ValidationException

# Israeli pension milestones
FULL_PENSION_AGE_MALE = 67
FULL_PENSION_AGE_FEMALE = 65


def _get_full_pension_age(gender: str) -> int:
    """Return full pension age based on gender (67 for male, 65 for female)."""
    return FULL_PENSION_AGE_FEMALE if gender == "female" else FULL_PENSION_AGE_MALE


class RetirementService:
    """Retirement planning projections and status calculations.

    Combines user-defined goals with real tracked data to produce
    FIRE number, projected net worth, and phase-based income analysis.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = RetirementGoalRepository(db)
        self.insurance_account_service = InsuranceAccountService(db)
        self.analysis_service = AnalysisService(db)
        self.investments_service = InvestmentsService(db)
        self.bank_balance_service = BankBalanceService(db)
        self.cash_balance_service = CashBalanceService(db)

    def get_goal(self) -> dict | None:
        """Get the retirement goal profile as a dict, or None."""
        goal = self.repo.get()
        if not goal:
            return None
        return {
            "id": goal.id,
            "current_age": goal.current_age,
            "gender": goal.gender,
            "target_retirement_age": goal.target_retirement_age,
            "life_expectancy": goal.life_expectancy,
            "monthly_expenses_in_retirement": goal.monthly_expenses_in_retirement,
            "inflation_rate": goal.inflation_rate,
            "expected_return_rate": goal.expected_return_rate,
            "withdrawal_rate": goal.withdrawal_rate,
            "pension_monthly_payout_estimate": goal.pension_monthly_payout_estimate,
            "keren_hishtalmut_balance": goal.keren_hishtalmut_balance,
            "keren_hishtalmut_monthly_contribution": goal.keren_hishtalmut_monthly_contribution,
            "bituach_leumi_eligible": bool(goal.bituach_leumi_eligible),
            "bituach_leumi_monthly_estimate": goal.bituach_leumi_monthly_estimate,
            "other_passive_income": goal.other_passive_income,
        }

    def upsert_goal(self, **fields) -> dict:
        """Create or update the retirement goal and return it as dict."""
        goal = self.repo.upsert(**fields)
        return self.get_goal()

    def get_keren_hishtalmut_scraped_balance(self) -> float | None:
        """Get total Keren Hishtalmut balance from scraped insurance data.

        Returns
        -------
        float or None
            Sum of all hishtalmut account balances, or None if no data.
        """
        return self.insurance_account_service.get_keren_hishtalmut_balance()

    def get_scraped_defaults(self) -> dict:
        """Get all auto-fillable values from scraped insurance data.

        For each field, returns the scraped value or None if unavailable.
        Monthly contributions are estimated from the last transaction amount
        of active accounts (those with transactions in the current or
        previous month).

        Returns
        -------
        dict
            Keys: keren_hishtalmut_balance, keren_hishtalmut_monthly_contribution,
            pension_monthly_deposit. Values are float or None.
        """
        return {
            "keren_hishtalmut_balance": (
                self.insurance_account_service.get_keren_hishtalmut_balance()
            ),
            "keren_hishtalmut_monthly_contribution": (
                self.insurance_account_service.get_monthly_contribution_by_type(
                    "hishtalmut"
                )
            ),
            "pension_monthly_deposit": (
                self.insurance_account_service.get_monthly_contribution_by_type(
                    "pension"
                )
            ),
        }

    def get_current_status(self) -> dict:
        """Aggregate current financial status from real dashboard data.

        Returns
        -------
        dict
            Keys: net_worth, avg_monthly_expenses, avg_monthly_income,
            savings_rate, total_investments, monthly_savings.
        """
        # Net worth from analysis
        net_worth_data = self.analysis_service.get_net_worth_over_time()
        current_net_worth = 0.0
        if net_worth_data:
            latest = net_worth_data[-1]
            current_net_worth = latest.get("net_worth", 0.0)

        # Income/expenses over time for averages
        monthly_data = self.analysis_service.get_income_expenses_over_time()
        avg_monthly_income = 0.0
        avg_monthly_expenses = 0.0
        monthly_savings = 0.0

        if monthly_data:
            # Use last 6 months for averages (or all if less)
            recent = monthly_data[-6:] if len(monthly_data) >= 6 else monthly_data
            avg_monthly_income = sum(m["income"] for m in recent) / len(recent)
            avg_monthly_expenses = sum(m["expenses"] for m in recent) / len(recent)
            monthly_savings = avg_monthly_income - avg_monthly_expenses

        savings_rate = (
            (monthly_savings / avg_monthly_income * 100)
            if avg_monthly_income > 0
            else 0.0
        )

        # Total investments
        overview = self.analysis_service.get_overview()
        total_investments = overview.get("total_investments", 0.0)

        return {
            "net_worth": current_net_worth,
            "avg_monthly_expenses": avg_monthly_expenses,
            "avg_monthly_income": avg_monthly_income,
            "savings_rate": round(savings_rate, 1),
            "total_investments": total_investments,
            "monthly_savings": monthly_savings,
        }

    def get_projections(self, goal_override: dict | None = None) -> dict:
        """Compute FIRE projections based on goal + real data.

        Parameters
        ----------
        goal_override : dict or None
            If provided, use these goal params instead of reading from DB.
            Allows preview calculations without saving.

        Returns
        -------
        dict
            Keys: fire_number, years_to_fire, fire_age,
            earliest_possible_retirement_age, monthly_savings_needed,
            progress_pct, readiness, net_worth_projection, income_projection.
        """
        goal_data = goal_override or self.get_goal()
        if not goal_data:
            raise EntityNotFoundException("Retirement goal not configured")

        status = self.get_current_status()

        # FIRE number: annual expenses / withdrawal rate
        annual_expenses = goal_data["monthly_expenses_in_retirement"] * 12
        fire_number = annual_expenses / goal_data["withdrawal_rate"]

        # Progress
        progress_pct = min(
            (status["net_worth"] / fire_number * 100) if fire_number > 0 else 0, 100
        )

        # Project net worth year by year
        net_worth_projection = self._project_net_worth(goal_data, status)

        # Find FIRE age (when net worth >= fire_number)
        years_to_fire = None
        fire_age = None
        for point in net_worth_projection:
            if point["net_worth_baseline"] >= fire_number:
                years_to_fire = point["age"] - goal_data["current_age"]
                fire_age = point["age"]
                break

        # If never reached within life expectancy
        if years_to_fire is None:
            years_to_fire = -1
            fire_age = -1

        # Earliest possible retirement age = FIRE age (baseline scenario)
        earliest_possible_retirement_age = fire_age

        # Monthly savings needed to hit target retirement age
        monthly_savings_needed = self._calc_required_monthly_savings(
            goal_data, status, fire_number
        )

        # Longevity check: does portfolio survive until life expectancy?
        portfolio_depleted_age = self._find_depletion_age(
            net_worth_projection, goal_data["life_expectancy"]
        )

        # Readiness traffic light (must both reach FIRE and survive drawdown)
        if fire_age != -1 and fire_age <= goal_data["target_retirement_age"]:
            if portfolio_depleted_age is not None:
                readiness = "off_track"
            else:
                readiness = "on_track"
        elif fire_age != -1 and fire_age <= goal_data["target_retirement_age"] + 5:
            if portfolio_depleted_age is not None:
                readiness = "off_track"
            else:
                readiness = "close"
        else:
            readiness = "off_track"

        # Retirement income projection (phase-based, from current age)
        income_projection = self._project_retirement_income(goal_data)

        return {
            "fire_number": round(fire_number, 0),
            "years_to_fire": years_to_fire,
            "fire_age": fire_age,
            "earliest_possible_retirement_age": earliest_possible_retirement_age,
            "monthly_savings_needed": round(monthly_savings_needed, 0),
            "progress_pct": round(progress_pct, 1),
            "readiness": readiness,
            "portfolio_depleted_age": portfolio_depleted_age,
            "target_retirement_age": goal_data["target_retirement_age"],
            "net_worth_projection": net_worth_projection,
            "income_projection": income_projection,
        }

    def _project_net_worth(self, goal: dict, status: dict) -> list[dict]:
        """Project net worth year-by-year with three scenarios.

        Parameters
        ----------
        goal : dict
            Retirement goal parameters.
        status : dict
            Current financial status from real data.

        Returns
        -------
        list[dict]
            Per-year projection with age, and net_worth for
            optimistic/baseline/conservative scenarios.
        """
        current_age = goal["current_age"]
        life_exp = goal["life_expectancy"]
        target_age = goal["target_retirement_age"]
        return_rate = goal["expected_return_rate"]
        inflation = goal["inflation_rate"]
        monthly_savings = status["monthly_savings"]
        annual_savings = monthly_savings * 12
        full_pension_age = _get_full_pension_age(goal.get("gender", "male"))

        # Keren Hishtalmut grows separately (tax-free)
        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]

        # Start from current net worth minus KH (tracked separately)
        base_nw = status["net_worth"] - kh_balance

        projections = []
        # Three return rate scenarios
        scenarios = {
            "optimistic": return_rate + 0.01,
            "baseline": return_rate,
            "conservative": return_rate - 0.01,
        }

        for scenario_name, rate in scenarios.items():
            nw = base_nw
            kh = kh_balance
            annual_expenses = goal["monthly_expenses_in_retirement"] * 12

            for year_offset in range(life_exp - current_age + 1):
                age = current_age + year_offset
                inflation_adjusted_expenses = annual_expenses * (
                    (1 + inflation) ** year_offset
                )

                if age < target_age:
                    # Accumulation phase: grow + save
                    nw = nw * (1 + rate) + annual_savings
                    kh = kh * (1 + rate) + kh_monthly * 12
                else:
                    # Drawdown phase: grow - withdraw + income sources
                    annual_income = goal["other_passive_income"] * 12
                    if age >= full_pension_age:
                        annual_income += goal["pension_monthly_payout_estimate"] * 12
                        if goal["bituach_leumi_eligible"]:
                            annual_income += (
                                goal["bituach_leumi_monthly_estimate"] * 12
                            )

                    withdrawal_needed = max(
                        0, inflation_adjusted_expenses - annual_income
                    )

                    # Draw from KH first (tax-free), then main portfolio
                    if kh > 0:
                        kh_draw = min(kh, withdrawal_needed)
                        kh -= kh_draw
                        withdrawal_needed -= kh_draw

                    nw = nw * (1 + rate) - withdrawal_needed
                    kh = kh * (1 + max(rate, 0))  # KH continues to grow

                total = nw + kh

                # Only append for one scenario, update for others
                if scenario_name == "optimistic":
                    projections.append(
                        {
                            "age": age,
                            "net_worth_optimistic": round(total, 0),
                            "net_worth_baseline": 0,
                            "net_worth_conservative": 0,
                        }
                    )
                else:
                    projections[year_offset][f"net_worth_{scenario_name}"] = round(
                        total, 0
                    )

        return projections

    def _project_retirement_income(self, goal: dict) -> list[dict]:
        """Project income sources by age (from current age to life expectancy).

        During accumulation (before target retirement age), shows salary/savings.
        During retirement, shows portfolio withdrawals + pension + BL + passive.

        Parameters
        ----------
        goal : dict
            Retirement goal parameters.

        Returns
        -------
        list[dict]
            Per-year income sources: salary_savings, portfolio_withdrawal,
            pension, bituach_leumi, passive_income, total_income, expenses.
        """
        current_age = goal["current_age"]
        target_age = goal["target_retirement_age"]
        life_exp = goal["life_expectancy"]
        inflation = goal["inflation_rate"]
        annual_expenses_base = goal["monthly_expenses_in_retirement"] * 12
        full_pension_age = _get_full_pension_age(goal.get("gender", "male"))

        result = []
        for age in range(current_age, life_exp + 1):
            years_from_now = age - current_age
            inflation_adjusted = annual_expenses_base * (
                (1 + inflation) ** years_from_now
            )

            pension = 0.0
            if age >= full_pension_age:
                pension = goal["pension_monthly_payout_estimate"] * 12

            bl = 0.0
            if age >= full_pension_age and goal["bituach_leumi_eligible"]:
                bl = goal["bituach_leumi_monthly_estimate"] * 12

            passive = goal["other_passive_income"] * 12

            # Before retirement: income comes from salary/savings
            # After retirement: income comes from portfolio + pension + BL + passive
            salary_savings = 0.0
            portfolio_withdrawal = 0.0
            if age < target_age:
                # Accumulation phase — no portfolio withdrawal needed
                salary_savings = inflation_adjusted
            else:
                non_portfolio = pension + bl + passive
                portfolio_withdrawal = max(0, inflation_adjusted - non_portfolio)

            non_portfolio = pension + bl + passive + salary_savings
            total_income = non_portfolio + portfolio_withdrawal

            result.append(
                {
                    "age": age,
                    "salary_savings": round(salary_savings, 0),
                    "portfolio_withdrawal": round(portfolio_withdrawal, 0),
                    "pension": round(pension, 0),
                    "bituach_leumi": round(bl, 0),
                    "passive_income": round(passive, 0),
                    "total_income": round(total_income, 0),
                    "expenses": round(inflation_adjusted, 0),
                }
            )

        return result

    def solve_all_fields(self, goal_override: dict | None = None) -> dict:
        """Solve for all adjustable fields to find values that reach FIRE.

        Parameters
        ----------
        goal_override : dict or None
            If provided, use these goal params instead of reading from DB.

        Returns
        -------
        dict
            Keys: target_retirement_age, monthly_expenses_in_retirement,
            expected_return_rate. Each value is the solved result or -1 if
            not achievable.
        """
        goal_data = goal_override or self.get_goal()
        if not goal_data:
            raise EntityNotFoundException("Retirement goal not configured")

        status = self.get_current_status()

        age = self._solve_target_retirement_age(goal_data, status)
        expenses = self._solve_monthly_expenses(goal_data, status)
        rate = self._solve_return_rate(goal_data, status)
        life_exp = self._solve_life_expectancy(goal_data, status)

        return {
            "target_retirement_age": age,
            "monthly_expenses_in_retirement": round(expenses, 0) if expenses != -1 else -1,
            "expected_return_rate": round(rate, 4) if rate != -1 else -1,
            "life_expectancy": life_exp,
        }

    def solve_for_field(self, field: str) -> dict:
        """Solve for a single field value that would reach FIRE at target age.

        Given all other fields fixed, compute the value of `field` such that
        projected net worth at target retirement age equals the FIRE number.

        Parameters
        ----------
        field : str
            One of: target_retirement_age, monthly_expenses_in_retirement,
            expected_return_rate.

        Returns
        -------
        dict
            Keys: field, value, unit.
        """
        goal_data = self.get_goal()
        if not goal_data:
            raise EntityNotFoundException("Retirement goal not configured")

        status = self.get_current_status()

        if field == "target_retirement_age":
            value = self._solve_target_retirement_age(goal_data, status)
            return {"field": field, "value": value, "unit": "age"}

        if field == "monthly_expenses_in_retirement":
            value = self._solve_monthly_expenses(goal_data, status)
            return {"field": field, "value": round(value, 0), "unit": "currency"}

        if field == "expected_return_rate":
            value = self._solve_return_rate(goal_data, status)
            return {"field": field, "value": round(value, 4), "unit": "rate"}

        if field == "life_expectancy":
            value = self._solve_life_expectancy(goal_data, status)
            return {"field": field, "value": value, "unit": "age"}

        raise ValidationException(f"Cannot auto-adjust field: {field}")

    def _survives_drawdown(self, goal: dict, status: dict) -> bool:
        """Check if portfolio survives through life expectancy.

        Runs the full projection and checks that baseline never hits zero.
        """
        projection = self._project_net_worth(goal, status)
        return self._find_depletion_age(projection, goal["life_expectancy"]) is None

    def _solve_target_retirement_age(self, goal: dict, status: dict) -> int:
        """Find earliest retirement age where portfolio survives to life expectancy.

        For each candidate age (starting from earliest FIRE-eligible), runs
        the full drawdown simulation to verify longevity.
        """
        annual_expenses = goal["monthly_expenses_in_retirement"] * 12
        fire_number = annual_expenses / goal["withdrawal_rate"]

        current_age = goal["current_age"]
        rate = goal["expected_return_rate"]
        monthly_savings = status["monthly_savings"]
        annual_savings = monthly_savings * 12
        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]
        base_nw = status["net_worth"] - kh_balance

        # First find earliest age where FIRE number is reached
        nw = base_nw
        kh = kh_balance
        fire_eligible_age = None
        for year_offset in range(goal["life_expectancy"] - current_age + 1):
            total = nw + kh
            if total >= fire_number:
                fire_eligible_age = current_age + year_offset
                break
            nw = nw * (1 + rate) + annual_savings
            kh = kh * (1 + rate) + kh_monthly * 12

        if fire_eligible_age is None:
            return -1

        # Now check each candidate age from fire_eligible_age onward
        # to find the earliest that also survives through life expectancy
        for candidate_age in range(fire_eligible_age, goal["life_expectancy"] + 1):
            test_goal = {**goal, "target_retirement_age": candidate_age}
            if self._survives_drawdown(test_goal, status):
                return candidate_age

        return -1  # Not reachable

    def _solve_monthly_expenses(self, goal: dict, status: dict) -> float:
        """Find max monthly expenses where portfolio survives to life expectancy.

        Uses binary search: upper bound from FIRE formula, then verifies
        drawdown longevity.
        """
        current_age = goal["current_age"]
        target_age = goal["target_retirement_age"]
        years = target_age - current_age
        if years <= 0:
            return 0.0

        rate = goal["expected_return_rate"]
        monthly_savings = status["monthly_savings"]
        annual_savings = monthly_savings * 12
        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]
        base_nw = status["net_worth"] - kh_balance

        nw = base_nw
        kh = kh_balance
        for _ in range(years):
            nw = nw * (1 + rate) + annual_savings
            kh = kh * (1 + rate) + kh_monthly * 12

        projected_nw = nw + kh
        # Upper bound: FIRE formula max (may not survive drawdown)
        max_monthly = (projected_nw * goal["withdrawal_rate"]) / 12
        if max_monthly <= 0:
            return 0.0

        # Binary search for max expenses that survive drawdown
        lo, hi = 0.0, max_monthly
        for _ in range(50):
            mid = (lo + hi) / 2
            test_goal = {**goal, "monthly_expenses_in_retirement": mid}
            if self._survives_drawdown(test_goal, status):
                lo = mid
            else:
                hi = mid
            if hi - lo < 100:  # converge to within 100 ILS
                break

        return lo

    def _solve_return_rate(self, goal: dict, status: dict) -> float:
        """Find minimum return rate where portfolio survives to life expectancy.

        Uses binary search over return rates, checking both FIRE number
        and drawdown longevity.
        """
        current_age = goal["current_age"]
        target_age = goal["target_retirement_age"]
        years = target_age - current_age
        if years <= 0:
            return 0.0

        # Binary search between -10% and 30%
        lo, hi = -0.10, 0.30

        # Check if achievable at max rate
        test_goal = {**goal, "expected_return_rate": hi}
        if not self._survives_drawdown(test_goal, status):
            return -1  # Not achievable even at 30%

        for _ in range(100):
            mid = (lo + hi) / 2
            test_goal = {**goal, "expected_return_rate": mid}
            if self._survives_drawdown(test_goal, status):
                hi = mid
            else:
                lo = mid
            if hi - lo < 0.00001:
                break

        return hi

    @staticmethod
    def _find_depletion_age(
        net_worth_projection: list[dict], life_expectancy: int
    ) -> int | None:
        """Find the age at which portfolio first drops to zero or below.

        Only checks baseline scenario during the drawdown phase.

        Returns
        -------
        int or None
            Age when portfolio is depleted, or None if it survives.
        """
        for point in net_worth_projection:
            if point["net_worth_baseline"] <= 0 and point["age"] <= life_expectancy:
                return point["age"]
        return None

    def _solve_life_expectancy(self, goal: dict, status: dict) -> int:
        """Find maximum life expectancy the portfolio can sustain.

        Runs the drawdown simulation and returns the last age before
        the baseline net worth goes to zero or below.

        Returns
        -------
        int
            Maximum sustainable life expectancy, or -1 if portfolio never
            depletes (or depletes before retirement).
        """
        projection = self._project_net_worth(goal, status)
        target_age = goal["target_retirement_age"]

        # Find last age with positive baseline balance after retirement
        last_sustainable_age = -1
        for point in projection:
            age = point["age"]
            if age < target_age:
                continue
            if point["net_worth_baseline"] > 0:
                last_sustainable_age = age
            else:
                break

        if last_sustainable_age == -1:
            return -1

        # If portfolio never depletes within the projection, return -1
        # (meaning "no limit needed")
        depletes = any(
            p["net_worth_baseline"] <= 0 and p["age"] > target_age
            for p in projection
        )
        if not depletes:
            return -1

        return last_sustainable_age

    def _calc_required_monthly_savings(
        self, goal: dict, status: dict, fire_number: float
    ) -> float:
        """Calculate monthly savings needed to reach FIRE number by target age.

        Uses future value of annuity formula to find the required periodic
        payment.

        Parameters
        ----------
        goal : dict
            Retirement goal parameters.
        status : dict
            Current financial status.
        fire_number : float
            Target portfolio size.

        Returns
        -------
        float
            Required monthly savings (0 if already on track).
        """
        years = goal["target_retirement_age"] - goal["current_age"]
        if years <= 0:
            return 0.0

        rate = goal["expected_return_rate"]
        current_nw = status["net_worth"]

        # Future value of current net worth
        fv_current = current_nw * ((1 + rate) ** years)

        # How much more is needed
        gap = fire_number - fv_current
        if gap <= 0:
            return 0.0

        # Monthly rate
        monthly_rate = (1 + rate) ** (1 / 12) - 1
        months = years * 12

        # Future value of annuity: PMT * ((1+r)^n - 1) / r
        if monthly_rate == 0:
            return gap / months

        fv_factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
        return gap / fv_factor
