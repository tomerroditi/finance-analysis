"""API tests for the early-retirement calculator.

The route is the seam between the reference's flat form payload and the engine:
it parses 70-odd form fields into a plan, runs the solver, and flattens the
result back into the rows the charts read. These drive that seam with the same
scenarios the engine is tested on, and assert the response carries the whole
monthly decomposition rather than a summary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = (Path(__file__).resolve().parents[3]
            / "research" / "zeke_retire_calc" / "fixtures")

BASELINE = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))["overrides"]

EVERYTHING = {
    **BASELINE,
    "dateOfBirth": "1985-03-01",
    "gender": "male",
    "balance": "180000",
    "cashBuffer": "40000",
    "creditLimit": "25000",
    "retireRule": "90",
    "base_problem_max_age": "62",
    "num_income_fields": "2",
    "incomeSum1": "48000", "incomeRise1": "1.5",
    "incomeStartType2": "one_time", "incomeStartDate2": "2034-06-01",
    "incomeSum2": "250000", "incomeRise2": "0.0", "incomeEndType2": "forever",
    "num_expense_fields": "2",
    "expenseSum1": "22000", "expenseRise1": "0.5",
    "expenseStartType2": "one_time", "expenseStartDate2": "2034-06-01",
    "expenseSum2": "90000", "expenseRise2": "0.0", "expenseEndType2": "forever",
    "num_portfolio_fields": "3",
    "portfolioBalance1": "900000", "portfolioProfitFraction1": "55",
    "portfolio_fifo_lifo1": "fifo", "portfolioInterest1": "6.5",
    "portfolio_goal1": "6000000", "portfolioDescription1": "Broker",
    "portfolioDesignation2": "mukeret_main", "portfolio_type2": "gemel",
    "portfolioBalance2": "250000", "portfolio_goal2": "2000000",
    "portfolioInterest2": "5.0", "portfolioFee2": "0.1",
    "portfolioProfitFraction2": "0", "portfolio_fifo_lifo2": "flat",
    "portfolioDescription2": "Gemel",
    "portfolioDesignation3": "goal", "portfolio_type3": "polisa",
    "portfolioBalance3": "300000", "portfolio_goal3": "1500000",
    "portfolioInterest3": "5.0", "portfolioFee3": "0.1",
    "portfolioProfitFraction3": "0", "portfolio_fifo_lifo3": "flat",
    "portfolioDescription3": "Polisa",
    "pensionBalance": "1100000", "pensionDeposit": "4200",
    "pension_tactics": "60-67", "percentage_mukeret": "30",
    "withdraw_pizuim": "on", "work_start_year": "2008",
    "num_keren_fields": "1", "kerenBalance1": "260000", "kerenDeposit1": "2400",
    "kerenInterest1": "5.0", "kerenFee1": "0.6", "kerenType1": "maslulit",
    "num_loan_fields": "1", "debtStartDate1": "2024-05-01",
    "debtInitialSum1": "900000", "debtTotalPeriod1": "25", "debtInterest1": "4.2",
    "debtType1": "spitzer",
    "num_realestate_fields": "1", "realestateValue1": "2400000",
    "realestateRise1": "1.2",
    "pensionTake_2": "on", "pensionName_2": "S", "gender_2": "female",
    "dateOfBirth_2": "1988-11-01", "pensionBalance_2": "700000",
    "pensionDeposit_2": "3100", "pension_tactics_2": "60",
    "percentage_mukeret_2": "45",
}
"""Every instrument at once, in the reference's own field names."""


def _calculate(client, fields, **extra):
    response = client.post("/api/fire/calculate", json={"fields": fields, **extra})
    assert response.status_code == 200, response.text
    return response.json()


class TestFireCalculate:
    """POST /api/fire/calculate."""

    def test_a_recorded_scenario_projects_to_the_horizon(self, test_client):
        """The baseline fixture runs and returns a full monthly series."""
        body = _calculate(test_client, BASELINE)
        assert body["status"] in {"success", "goals_not_met"}
        assert body["months"], "the projection must carry its months"
        assert body["months"][-1]["age"] == pytest.approx(81.0)
        assert body["retire_age"] is not None
        assert any(g["key"] == "living_expenses" for g in body["goals"])

    def test_the_monthly_rows_carry_the_whole_decomposition(self, test_client):
        """Every month's income and expense rows balance, over the wire."""
        body = _calculate(test_client, EVERYTHING)
        for row in body["months"]:
            assert sum(row["incomes"].values()) == pytest.approx(
                sum(row["expenses"].values()), abs=1e-6)
            assert row["net_worth"] == pytest.approx(
                sum(row["assets"].values()) - row["liabilities"])

    def test_every_instrument_shows_up_in_the_response(self, test_client):
        """A scenario using everything must return rows for everything."""
        body = _calculate(test_client, EVERYTHING)
        keys = set()
        for row in body["months"]:
            keys.update(k for k, v in row["incomes"].items() if v)
            keys.update(k for k, v in row["expenses"].items() if v)
            keys.update(k for k, v in row["assets"].items() if v)
        for expected in ("work", "one_time", "living", "loans", "state_pension",
                         "state_pension_partner", "keren0", "pension0", "realestate0"):
            assert expected in keys, f"{expected} never appeared"
        assert any(k.startswith("gemel") for k in keys)

    def test_a_supplied_decumulation_return_is_honoured(self, test_client):
        """The override exists so a caller can pin one scenario's rate."""
        low = _calculate(test_client, BASELINE, decumulation_return_pct=0.0)
        high = _calculate(test_client, BASELINE, decumulation_return_pct=4.0)
        assert high["months"][-1]["net_worth"] > low["months"][-1]["net_worth"]

    def test_a_person_past_the_horizon_gets_no_result(self, test_client):
        """The reference answers "no results" rather than an empty chart."""
        body = _calculate(test_client, {**BASELINE, "dateOfBirth": "1930-01-01"})
        assert body["status"] == "no_result"
        assert body["months"] == []

    def test_an_unaffordable_plan_reports_its_goals_unmet(self, test_client):
        """Failure is a verdict, not an error."""
        body = _calculate(test_client, {
            **BASELINE, "incomeSum1": "1000", "expenseSum1": "40000",
            "portfolioBalance1": "0", "balance": "0"})
        assert body["status"] == "goals_not_met"
        assert any(not g["met"] for g in body["goals"])

    @pytest.mark.parametrize("bad", [
        {"dateOfBirth": "not-a-date"},
        {"portfolioInterest1": "abc"},
        {"portfolio_type1": "crypto"},
        {"pensionBalance": "500000", "pension_tactics": "75"},
    ])
    def test_malformed_input_is_a_client_error(self, test_client, bad):
        """A bad field must name itself in a 4xx, not surface as a 500."""
        response = test_client.post(
            "/api/fire/calculate", json={"fields": {**BASELINE, **bad}})
        assert response.status_code in {400, 422}, response.text
        assert any(field in response.text for field in bad)

    def test_a_nonsense_row_count_means_no_rows(self, test_client):
        """How many rows the form had is a UI detail, not part of the plan."""
        body = _calculate(test_client, {**BASELINE, "num_portfolio_fields": "-1"})
        assert body["status"] in {"success", "goals_not_met"}
        assert all(not any(k.startswith("portfolio") for k in row["assets"])
                   for row in body["months"])
