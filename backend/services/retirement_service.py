"""
Retirement planning business logic.

Computes FIRE projections, net worth trajectories, and retirement income
phase analysis for the Israeli financial context.

All projections are computed in REAL terms (today's purchasing power):
the user's nominal expected return is converted to a real rate via
``(1 + nominal) / (1 + inflation) - 1``, and expenses, savings, pension,
Bituach Leumi and passive income are held constant in today's shekels
(salaries and Israeli pension/BL payouts are CPI-indexed in practice).
This keeps every displayed amount — including the FIRE number, which is
derived from today's expenses — directly comparable across the whole
projection horizon.
"""

import pandas as pd
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


def _real_rate(nominal: float, inflation: float) -> float:
    """Convert a nominal annual return to a real (inflation-adjusted) rate."""
    return (1 + nominal) / (1 + inflation) - 1


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
            "monthly_income": goal.monthly_income,
            "net_worth_override": goal.net_worth_override,
            "monthly_expenses_override": goal.monthly_expenses_override,
            "total_investments_override": goal.total_investments_override,
        }

    def upsert_goal(self, **fields) -> dict:
        """Create or update the retirement goal and return it as dict."""
        self.repo.upsert(**fields)
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
            "avg_monthly_salary": self.analysis_service.get_avg_monthly_salary(),
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
            # Complete months only. The running month has partial income (no
            # salary yet, early in the month) but near-full expenses, so
            # including it understated monthly_savings — which drives the
            # entire FIRE projection, savings_rate and monthly_savings_needed.
            current_month = pd.Timestamp.today().strftime("%Y-%m")
            complete_months = [
                m for m in monthly_data if m["month"] < current_month
            ] or monthly_data

            monthly_data = complete_months
            # Income: last 6 months average (or all if fewer).
            recent_income = (
                monthly_data[-6:] if len(monthly_data) >= 6 else monthly_data
            )
            avg_monthly_income = sum(
                m["income"] for m in recent_income
            ) / len(recent_income)
            # Expenses: last 12 months average (or all if fewer) — a full
            # year smooths out seasonal spikes (holidays, annual fees).
            recent_expenses = (
                monthly_data[-12:] if len(monthly_data) >= 12 else monthly_data
            )
            avg_monthly_expenses = sum(
                m["expenses"] for m in recent_expenses
            ) / len(recent_expenses)
            monthly_savings = avg_monthly_income - avg_monthly_expenses

        savings_rate = (
            (monthly_savings / avg_monthly_income * 100)
            if avg_monthly_income > 0
            else 0.0
        )

        # Total investments
        overview = self.analysis_service.get_overview()
        total_investments = overview.get("total_investments", 0.0)

        # Keren Hishtalmut value that is ALREADY inside the tracked net
        # worth: scraped KH policies are auto-synced into the investments
        # table with scraped balance snapshots (InsuranceSyncMixin), and the
        # net worth series values investments snapshot-first. The FIRE
        # projection models KH as its own bucket (goal field), so this
        # amount must be moved out of the base portfolio to avoid double
        # counting. For users who only typed a KH balance (nothing synced),
        # this is 0 and their KH counts on top of net worth.
        tracked_kh_value = 0.0
        for inv in self.investments_service.get_all_investments():
            if inv.get("type") == "hishtalmut":
                tracked_kh_value += self.investments_service.calculate_current_balance(
                    int(inv["id"])
                )

        return {
            "net_worth": current_net_worth,
            "avg_monthly_expenses": avg_monthly_expenses,
            "avg_monthly_income": avg_monthly_income,
            "savings_rate": round(savings_rate, 1),
            "total_investments": total_investments,
            "monthly_savings": monthly_savings,
            "tracked_kh_value": tracked_kh_value,
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

        status = self._effective_status(goal_data)

        # FIRE number: annual expenses / withdrawal rate (today's shekels)
        annual_expenses = goal_data["monthly_expenses_in_retirement"] * 12
        fire_number = annual_expenses / goal_data["withdrawal_rate"]

        # Progress toward the FIRE number counts total wealth: tracked net
        # worth (with any synced KH investments swapped out) plus the goal's
        # KH balance, so KH counts exactly once whether it was scraped into
        # the investments table or only typed into the goal.
        total_wealth = (
            status["net_worth"]
            - status.get("tracked_kh_value", 0.0)
            + goal_data["keren_hishtalmut_balance"]
        )
        # Clamped to [0, 100]: negative wealth would otherwise emit a
        # negative percentage, which the UI progress bar renders as an
        # invalid CSS width (visually a FULL bar).
        progress_pct = min(
            max((total_wealth / fire_number * 100) if fire_number > 0 else 0, 0),
            100,
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
            net_worth_projection,
            goal_data["life_expectancy"],
            goal_data["target_retirement_age"],
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
            # Gender-resolved (67 male / 65 female) — the chart's pension-age
            # marker must match where pension income actually starts.
            "full_pension_age": _get_full_pension_age(
                goal_data.get("gender", "male")
            ),
            "net_worth_projection": net_worth_projection,
            "income_projection": income_projection,
        }

    def _effective_status(self, goal_data: dict) -> dict:
        """Current status with the goal's manual overrides applied.

        The goal can override net worth, monthly income and monthly expenses
        (0 / None = use calculated). Projections AND solvers must both use
        this so suggestions stay consistent with the projections shown next
        to them.
        """
        status = self.get_current_status()

        if goal_data.get("net_worth_override"):
            status = {**status, "net_worth": goal_data["net_worth_override"]}

        effective_expenses = (
            goal_data["monthly_expenses_override"]
            if goal_data.get("monthly_expenses_override")
            else status["avg_monthly_expenses"]
        )
        effective_income = (
            goal_data["monthly_income"]
            if goal_data.get("monthly_income")
            else status["avg_monthly_income"]
        )

        if goal_data.get("monthly_income") or goal_data.get("monthly_expenses_override"):
            monthly_savings = effective_income - effective_expenses
            savings_rate = (
                round(monthly_savings / effective_income * 100, 1)
                if effective_income > 0
                else 0.0
            )
            status = {
                **status,
                "avg_monthly_income": effective_income,
                "avg_monthly_expenses": effective_expenses,
                "monthly_savings": monthly_savings,
                "savings_rate": savings_rate,
            }

        return status

    def _project_net_worth(self, goal: dict, status: dict) -> list[dict]:
        """Project net worth year-by-year with three scenarios, in real terms.

        All amounts are in today's shekels: each scenario's nominal return is
        converted to a real rate, and expenses, savings and retirement income
        sources are held constant (CPI-indexed in practice).

        KH is modelled as its own bucket (drawn first in retirement — it is
        tax-free), seeded from the goal's KH balance. Whatever KH value is
        already inside the tracked net worth (scraped policies auto-synced
        into the investments table — ``status["tracked_kh_value"]``) is
        removed from the base portfolio so it isn't counted twice; a KH
        balance that was only typed into the goal sits fully on top.

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

        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]
        base_nw = status["net_worth"] - status.get("tracked_kh_value", 0.0)

        annual_expenses = goal["monthly_expenses_in_retirement"] * 12

        projections = []
        # Three return scenarios: ±1% on the nominal rate, then converted to
        # real so the projection stays in today's shekels.
        scenarios = {
            "optimistic": _real_rate(return_rate + 0.01, inflation),
            "baseline": _real_rate(return_rate, inflation),
            "conservative": _real_rate(return_rate - 0.01, inflation),
        }

        for scenario_name, rate in scenarios.items():
            nw = base_nw
            kh = kh_balance

            for year_offset in range(life_exp - current_age + 1):
                age = current_age + year_offset

                # Record the balance the user HAS at this age, before applying
                # this year's growth. Recording after the growth step labelled
                # today's point with a year of compounding already applied,
                # which shifted the whole curve — and `fire_age` — a year early.
                total = nw + kh
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

                if age < target_age:
                    # Accumulation phase: grow + save
                    nw = nw * (1 + rate) + annual_savings
                    kh = kh * (1 + rate) + kh_monthly * 12
                else:
                    # Drawdown phase: grow, then withdraw net-of-income needs
                    annual_income = goal["other_passive_income"] * 12
                    if age >= full_pension_age:
                        annual_income += goal["pension_monthly_payout_estimate"] * 12
                        if goal["bituach_leumi_eligible"]:
                            annual_income += (
                                goal["bituach_leumi_monthly_estimate"] * 12
                            )

                    withdrawal_needed = max(0, annual_expenses - annual_income)

                    # Both buckets grow for the year, then the withdrawal
                    # comes out — KH first (tax-free), remainder from the
                    # main portfolio.
                    nw = nw * (1 + rate)
                    kh = kh * (1 + rate)
                    kh_draw = min(kh, withdrawal_needed) if kh > 0 else 0.0
                    kh -= kh_draw
                    nw -= withdrawal_needed - kh_draw

        return projections

    def _project_retirement_income(self, goal: dict) -> list[dict]:
        """Project income sources by age (from current age to life expectancy).

        During accumulation (before target retirement age), shows salary/savings.
        During retirement, shows portfolio withdrawals + pension + BL + passive.
        All amounts are in today's shekels (real terms), matching the net
        worth projection — expenses and CPI-indexed income sources are
        constant across the horizon.

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
        annual_expenses = goal["monthly_expenses_in_retirement"] * 12
        full_pension_age = _get_full_pension_age(goal.get("gender", "male"))

        result = []
        for age in range(current_age, life_exp + 1):
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
                salary_savings = annual_expenses
            else:
                non_portfolio = pension + bl + passive
                portfolio_withdrawal = max(0, annual_expenses - non_portfolio)

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
                    "expenses": round(annual_expenses, 0),
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

        status = self._effective_status(goal_data)

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

        status = self._effective_status(goal_data)

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
        return (
            self._find_depletion_age(
                projection, goal["life_expectancy"], goal["target_retirement_age"]
            )
            is None
        )

    def _plan_on_track(self, goal: dict, status: dict) -> bool:
        """Whether a plan reaches FIRE by its target age AND survives drawdown.

        This mirrors the readiness == "on_track" criteria in
        :meth:`get_projections`. Solvers must search against this predicate,
        not drawdown survival alone: a small pension-covered plan can survive
        at ANY return rate without ever reaching the FIRE number, and a
        survival-only search then converges to a meaningless answer.
        """
        fire_number = (
            goal["monthly_expenses_in_retirement"] * 12 / goal["withdrawal_rate"]
        )
        projection = self._project_net_worth(goal, status)
        fire_reached_by_target = any(
            point["age"] <= goal["target_retirement_age"]
            and point["net_worth_baseline"] >= fire_number
            for point in projection
        )
        if not fire_reached_by_target:
            return False
        return (
            self._find_depletion_age(
                projection, goal["life_expectancy"], goal["target_retirement_age"]
            )
            is None
        )

    def _solve_target_retirement_age(self, goal: dict, status: dict) -> int:
        """Find earliest retirement age where the plan is fully on track.

        For each candidate age (starting from earliest FIRE-eligible), runs
        the full simulation to verify both FIRE-by-candidate-age and
        drawdown longevity.
        """
        annual_expenses = goal["monthly_expenses_in_retirement"] * 12
        fire_number = annual_expenses / goal["withdrawal_rate"]

        current_age = goal["current_age"]
        rate = _real_rate(goal["expected_return_rate"], goal["inflation_rate"])
        monthly_savings = status["monthly_savings"]
        annual_savings = monthly_savings * 12
        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]

        # First find earliest age where FIRE number is reached (KH bucket
        # swaps out any synced KH value — see _project_net_worth)
        nw = status["net_worth"] - status.get("tracked_kh_value", 0.0)
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
        # to find the earliest whose plan is fully on track
        for candidate_age in range(fire_eligible_age, goal["life_expectancy"] + 1):
            test_goal = {**goal, "target_retirement_age": candidate_age}
            if self._plan_on_track(test_goal, status):
                return candidate_age

        return -1  # Not reachable

    def _solve_monthly_expenses(self, goal: dict, status: dict) -> float:
        """Find max monthly retirement expenses where the plan stays on track.

        Uses binary search: upper bound from the FIRE formula applied to the
        projected wealth at target age, then verifies FIRE-by-target-age and
        drawdown longevity together.

        Returns -1 when no positive expense level works (already at/past the
        target age, or projected wealth never supports any spending) — the
        UI filters -1 out; a literal "0 ILS/month" suggestion is noise.
        """
        current_age = goal["current_age"]
        target_age = goal["target_retirement_age"]
        years = target_age - current_age
        if years <= 0:
            return -1

        rate = _real_rate(goal["expected_return_rate"], goal["inflation_rate"])
        monthly_savings = status["monthly_savings"]
        annual_savings = monthly_savings * 12
        kh_balance = goal["keren_hishtalmut_balance"]
        kh_monthly = goal["keren_hishtalmut_monthly_contribution"]

        nw = status["net_worth"] - status.get("tracked_kh_value", 0.0)
        kh = kh_balance
        for _ in range(years):
            nw = nw * (1 + rate) + annual_savings
            kh = kh * (1 + rate) + kh_monthly * 12

        projected_nw = nw + kh
        # Upper bound: FIRE formula max (may not survive drawdown)
        max_monthly = (projected_nw * goal["withdrawal_rate"]) / 12
        if max_monthly <= 0:
            return -1

        # Binary search for max expenses that keep the plan on track
        lo, hi = 0.0, max_monthly
        for _ in range(50):
            mid = (lo + hi) / 2
            test_goal = {**goal, "monthly_expenses_in_retirement": mid}
            if self._plan_on_track(test_goal, status):
                lo = mid
            else:
                hi = mid
            if hi - lo < 100:  # converge to within 100 ILS
                break

        # lo > 0 was verified on-track by the search; lo == 0 means not even
        # a token spending level works (e.g. wealth stays negative to target)
        return lo if lo > 0 else -1

    def _solve_return_rate(self, goal: dict, status: dict) -> float:
        """Find minimum nominal return rate where the plan is on track.

        Uses binary search over return rates, requiring both FIRE by the
        target age and drawdown longevity (survival alone is trivially true
        for pension-covered plans and would converge to the search floor).

        Returns -1 when not achievable at any rate up to 30%, or when the
        target age is already at/behind the current age (no return rate can
        retire someone in the past) — the UI filters -1 out.
        """
        current_age = goal["current_age"]
        target_age = goal["target_retirement_age"]
        years = target_age - current_age
        if years <= 0:
            return -1

        # Binary search between -10% and 30%
        lo, hi = -0.10, 0.30

        # Check if achievable at max rate
        test_goal = {**goal, "expected_return_rate": hi}
        if not self._plan_on_track(test_goal, status):
            return -1  # Not achievable even at 30%

        for _ in range(100):
            mid = (lo + hi) / 2
            test_goal = {**goal, "expected_return_rate": mid}
            if self._plan_on_track(test_goal, status):
                hi = mid
            else:
                lo = mid
            if hi - lo < 0.00001:
                break

        return hi

    @staticmethod
    def _find_depletion_age(
        net_worth_projection: list[dict],
        life_expectancy: int,
        target_retirement_age: int | None = None,
    ) -> int | None:
        """Find the age at which portfolio first drops to zero or below.

        Only the drawdown phase counts. During accumulation a negative
        balance is normal — anyone carrying a mortgage or loans has a
        negative net worth today — and it says nothing about whether the
        plan survives retirement.

        Parameters
        ----------
        net_worth_projection : list[dict]
            Points from :meth:`_project_net_worth`.
        life_expectancy : int
            Upper age bound to consider.
        target_retirement_age : int or None
            Age drawdown begins. Points before it are ignored. ``None``
            keeps the legacy behaviour of scanning every point.

        Returns
        -------
        int or None
            Age when portfolio is depleted, or None if it survives.
        """
        for point in net_worth_projection:
            if target_retirement_age is not None and point["age"] < target_retirement_age:
                continue
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
            depletes (or depletes before retirement), or -1 when the FIRE
            number is never reached by the target age — a shorter life
            expectancy cannot fix a plan that never reaches FIRE, so
            suggesting one would be misleading.
        """
        projection = self._project_net_worth(goal, status)
        target_age = goal["target_retirement_age"]

        fire_number = (
            goal["monthly_expenses_in_retirement"] * 12 / goal["withdrawal_rate"]
        )
        fire_reached_by_target = any(
            point["age"] <= target_age
            and point["net_worth_baseline"] >= fire_number
            for point in projection
        )
        if not fire_reached_by_target:
            return -1

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
        """Calculate ADDITIONAL monthly savings needed to reach FIRE by target age.

        Credits the future value of current total wealth (tracked net worth
        + Keren Hishtalmut) and of the contributions the user is already
        making (monthly savings + KH deposits), then converts any remaining
        gap into an extra end-of-year annuity payment matching the
        projection's discrete annual model. All in real terms.

        Parameters
        ----------
        goal : dict
            Retirement goal parameters.
        status : dict
            Current financial status.
        fire_number : float
            Target portfolio size (today's shekels).

        Returns
        -------
        float
            Required EXTRA monthly savings beyond current ones (0 if the
            current plan already reaches the FIRE number by target age).
        """
        years = goal["target_retirement_age"] - goal["current_age"]
        if years <= 0:
            return 0.0

        rate = _real_rate(goal["expected_return_rate"], goal["inflation_rate"])
        current_wealth = (
            status["net_worth"]
            - status.get("tracked_kh_value", 0.0)
            + goal["keren_hishtalmut_balance"]
        )

        # Future value of what the user has today
        fv_current = current_wealth * ((1 + rate) ** years)

        # Future value factor of an end-of-year annuity — the same discrete
        # annual-deposit model _project_net_worth uses, so "0 extra needed"
        # agrees with the projection reaching FIRE at the target age.
        if rate == 0:
            fv_factor = float(years)
        else:
            fv_factor = ((1 + rate) ** years - 1) / rate

        current_annual_contribution = (
            status["monthly_savings"]
            + goal["keren_hishtalmut_monthly_contribution"]
        ) * 12
        fv_contributions = current_annual_contribution * fv_factor

        gap = fire_number - fv_current - fv_contributions
        if gap <= 0:
            return 0.0

        return gap / fv_factor / 12
