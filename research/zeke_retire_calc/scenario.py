"""Build complete reference form payloads from a structured description.

The reference rejects a submission with a missing per-row field outright
(`כשל בביצוע` — "execution failed", no job, no charts), and a hand-written
override dict is exactly where a row's `portfolio_deposit2` gets forgotten: the
first gemel ladder was lost that way. Every row built here carries every field
the reference's own add-row template has, defaulted to what that template
defaults it to, so a scenario only states what it varies.

    form(portfolios=[portfolio(balance=1_200_000)],
         pension=pension(balance=1_200_000, tactic="60-67", frozen=True),
         retire_at=45)

Field names and defaults were read off `/calculators/retire_table_action/
add_line/<type>/1` for each row type.
"""
from __future__ import annotations

from typing import Any

PERSON = {"dateOfBirth": "1990-01-01", "pensionName": "T", "gender": "male",
          "is_american": "no"}

PLAN = {"base_problem": "retire_asap", "base_problem_max_age": "60",
        "base_problem_cash_improve": "0", "base_problem_risk_increase": "0",
        "retireRule": "85", "prati_hishtalmut_order": "prati",
        "balance": "0", "cashBuffer": "0", "creditLimit": "0"}


def flow(amount: float, start: str = "now", end: str = "forever", rise: float = 0.0,
         start_date: str = "", end_date: str = "", description: str = "") -> dict:
    """An income or expense row."""
    return {"Sum": amount, "StartType": start, "StartDate": start_date,
            "EndType": end, "EndDate": end_date, "Rise": rise,
            "Description": description}


def portfolio(balance: float = 0, designation: str = "withdraw", kind: str = "portfolio",
              deposit_cap: float | str = "", goal: float = 0, interest: float = 5.0,
              fee: float = 0.1, profit_pct: float = 0.0, lots: str = "flat",
              description: str = "") -> dict:
    """A portfolio row. `profit_pct` is the reference's percent-of-balance field."""
    return {"portfolioBalance": balance, "portfolioDesignation": designation,
            "portfolio_type": kind, "portfolio_deposit": deposit_cap,
            "portfolio_goal": goal, "portfolioInterest": interest, "portfolioFee": fee,
            "portfolioProfitFraction": profit_pct, "portfolio_fifo_lifo": lots,
            "portfolioDescription": description}


def keren(balance: float = 0, deposit: float = 0, interest: float = 5.0, fee: float = 0.6,
          kind: str = "maslulit", end: str = "fire", end_date: str = "") -> dict:
    """A study-fund (Keren Hishtalmut) row."""
    return {"kerenBalance": balance, "kerenDeposit": deposit, "kerenInterest": interest,
            "kerenFee": fee, "kerenType": kind, "kerenEndType": end,
            "kerenEndDate": end_date}


def loan(amount: float, years: float, interest: float = 3.0, kind: str = "spitzer",
         start_date: str = "2026-09-01") -> dict:
    """A loan row."""
    return {"debtInitialSum": amount, "debtTotalPeriod": years, "debtInterest": interest,
            "debtType": kind, "debtStartDate": start_date}


def realestate(value: float, rise: float = 0.0) -> dict:
    """A real-estate row."""
    return {"realestateValue": value, "realestateRise": rise}


def pension(balance: float = 0, deposit: float = 0, interest: float = 7.0,
            fee_balance: float = 0.05, fee_deposit: float = 1.5, tactic: str = "60",
            mukeret_pct: float = 30, end: str = "fire", end_date: str = "",
            withdraw_severance: bool = False, work_start_year: int | str = "",
            frozen: bool = False) -> dict:
    """The main person's pension fund.

    `frozen` zeroes growth, fees and deposits, so the balance at annuitisation
    is exactly what was typed and the annuity is exactly balance / factor.
    """
    if frozen:
        deposit, interest, fee_balance, fee_deposit = 0, 0.0, 0.0, 0.0
    return {"pensionBalance": balance, "pensionDeposit": deposit,
            "pensionInterest": interest, "pensionFee1": fee_balance,
            "pensionFee2": fee_deposit, "pension_tactics": tactic,
            "percentage_mukeret": mukeret_pct, "pensionEndType": end,
            "pensionEndDate": end_date,
            "withdraw_pizuim": "on" if withdraw_severance else None,
            "work_start_year": work_start_year}


def _partner_pension(fields: dict) -> dict:
    """The same pension dict, renamed to the partner's `_2` fields."""
    out = {}
    for key, value in fields.items():
        if key == "pensionEndType":
            out["pensionEndType2"] = value
        else:
            out[f"{key}_2"] = value
    return out


def form(*, incomes: list[dict] | None = None, expenses: list[dict] | None = None,
         portfolios: list[dict] | None = None, kranot: list[dict] | None = None,
         loans: list[dict] | None = None, realestates: list[dict] | None = None,
         pension: dict | None = None, partner: dict | None = None,
         partner_pension: dict | None = None, retire_at: float | None = None,
         **fields: Any) -> dict[str, str]:
    """A full form payload.

    `retire_at` pins the retirement age (`retire_at_age`). `partner` is a dict
    of the partner's person fields (`dateOfBirth`, `gender`, `pensionName`);
    passing it turns the second person on. Any other keyword is a raw form
    field and wins over everything above.
    """
    incomes = [flow(10_000, "now", "fire")] if incomes is None else incomes
    expenses = [flow(5_000)] if expenses is None else expenses
    portfolios = [portfolio(100_000)] if portfolios is None else portfolios
    out: dict[str, Any] = {**PERSON, **PLAN}

    def rows(prefix: str, items: list[dict], count_key: str, joiner=None) -> None:
        out[count_key] = len(items)
        for index, item in enumerate(items, start=1):
            for key, value in item.items():
                out[joiner(key, index) if joiner else f"{prefix}{key}{index}"] = value

    rows("income", incomes, "num_income_fields")
    rows("expense", expenses, "num_expense_fields")
    rows("", portfolios, "num_portfolio_fields", lambda k, i: f"{k}{i}")
    rows("", kranot or [], "num_keren_fields", lambda k, i: f"{k}{i}")
    rows("", loans or [], "num_loan_fields", lambda k, i: f"{k}{i}")
    rows("", realestates or [], "num_realestate_fields", lambda k, i: f"{k}{i}")

    main = pension if pension is not None else globals()["pension"]()
    for key, value in main.items():
        out["pensionEndType1" if key == "pensionEndType" else key] = value
    if partner is not None:
        out["pensionTake_2"] = "on"
        out.update({f"{k}_2": v for k, v in {**PERSON, "pensionName": "P", **partner}.items()})
        out.update(_partner_pension(partner_pension or globals()["pension"]()))
    if retire_at is not None:
        out["base_problem"] = "retire_at_age"
        out["wanted_retire_age"] = retire_at
    out.update(fields)
    # An unchecked checkbox is absent from a real submission, not empty.
    return {key: str(value) for key, value in out.items() if value is not None}
