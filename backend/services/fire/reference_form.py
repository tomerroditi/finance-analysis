"""Translate a reference-calculator form payload into a :class:`Plan`.

The reference posts a flat, 1-indexed form (``portfolioBalance1``,
``expenseSum2``, ``num_portfolio_fields`` ...). Recorded fixtures store exactly
that payload, so this module is what lets a recorded reference run be replayed
through our engine. It is the single source of truth for the mapping — both the
parity tests and the research comparison tool use it.
"""

from __future__ import annotations

from datetime import date

from backend.errors import ValidationException

from backend.services.fire.models import (
    BaseProblem,
    CashFlow,
    EndType,
    Gender,
    KerenHishtalmut,
    KerenType,
    Loan,
    LoanType,
    LotMethod,
    Pension,
    PensionTactic,
    Person,
    Plan,
    Portfolio,
    PortfolioDesignation,
    PortfolioType,
    RealEstate,
    StartType,
)


def _num(payload: dict, key: str, default: float | None = 0.0) -> float | None:
    """Numeric field, with blank treated as "unset" rather than zero."""
    value = payload.get(key, default)
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationException(f"{key} must be a number, got {value!r}") from exc


def _req(payload: dict, key: str, default: float = 0.0) -> float:
    """Numeric field that must end up as a number."""
    value = _num(payload, key, default)
    return default if value is None else value


def _choice(enum, raw, key: str):
    """One of a field's fixed options, or a 400 naming the field."""
    try:
        return enum(raw)
    except ValueError as exc:
        options = ", ".join(member.value for member in enum)
        raise ValidationException(
            f"{key} must be one of {options}, got {raw!r}") from exc


def _date(payload: dict, key: str) -> date | None:
    raw = payload.get(key)
    if not raw:
        return None
    try:
        year, month, day = map(int, str(raw).split("-"))
        return date(year, month, day)
    except ValueError as exc:
        raise ValidationException(f"{key} must be a date, got {raw!r}") from exc


def _count(payload: dict, key: str, default: int = 0) -> int:
    """How many repeated rows to read. Junk falls back to the default.

    A row counter is a UI detail rather than a number the plan depends on, so a
    negative or unreadable one means "none of those rows" instead of an error.
    """
    try:
        return max(int(payload.get(key, default) or default), 0)
    except (TypeError, ValueError):
        return default


def _flow(payload: dict, prefix: str, index: int, default_end: str) -> CashFlow:
    return CashFlow(
        amount=_req(payload, f"{prefix}Sum{index}"),
        start_type=_choice(StartType, payload.get(f"{prefix}StartType{index}", "now"), f"{prefix}StartType{index}"),
        start_date=_date(payload, f"{prefix}StartDate{index}"),
        end_type=_choice(EndType, payload.get(f"{prefix}EndType{index}", default_end), f"{prefix}EndType{index}"),
        end_date=_date(payload, f"{prefix}EndDate{index}"),
        annual_rise_pct=_req(payload, f"{prefix}Rise{index}"),
        description=payload.get(f"{prefix}Description{index}", ""),
    )


def _portfolio(payload: dict, index: int) -> Portfolio:
    return Portfolio(
        balance=_req(payload, f"portfolioBalance{index}"),
        designation=_choice(PortfolioDesignation, payload.get(f"portfolioDesignation{index}", "withdraw"),
                                    f"portfolioDesignation{index}"),
        kind=_choice(PortfolioType, payload.get(f"portfolio_type{index}", "portfolio"),
                     f"portfolio_type{index}"),
        monthly_deposit_cap=_num(payload, f"portfolio_deposit{index}", None),
        goal=_req(payload, f"portfolio_goal{index}"),
        annual_return_pct=_req(payload, f"portfolioInterest{index}", 5.0),
        annual_fee_pct=_req(payload, f"portfolioFee{index}", 0.1),
        profit_fraction_pct=_req(payload, f"portfolioProfitFraction{index}"),
        lot_method=_choice(LotMethod, payload.get(f"portfolio_fifo_lifo{index}", "flat"),
                           f"portfolio_fifo_lifo{index}"),
        description=payload.get(f"portfolioDescription{index}", ""),
    )


def _pension(payload: dict, suffix: str, tactic_key: str, end_key: str) -> Pension | None:
    balance = _req(payload, f"pensionBalance{suffix}")
    deposit = _req(payload, f"pensionDeposit{suffix}")
    if not balance and not deposit:
        return None
    return Pension(
        balance=balance,
        monthly_deposit=deposit,
        fee_on_balance_pct=_req(payload, f"pensionFee1{suffix}", 0.05),
        fee_on_deposit_pct=_req(payload, f"pensionFee2{suffix}", 1.5),
        annual_return_pct=_req(payload, f"pensionInterest{suffix}", 7.0),
        tactic=_choice(PensionTactic, payload.get(tactic_key, "60"), tactic_key),
        mukeret_pct=_req(payload, f"percentage_mukeret{suffix}", 30.0),
        end_type=_choice(EndType, payload.get(end_key, "fire"), end_key),
        end_date=_date(payload, f"pensionEndDate{suffix}"),
        withdraw_severance=bool(payload.get(f"withdraw_pizuim{suffix}")),
        work_start_year=int(_num(payload, f"work_start_year{suffix}", None) or 0) or None,
    )


def plan_from_reference(payload: dict) -> Plan:
    """Build a :class:`Plan` from a reference form payload."""
    person = Person(
        name=payload.get("pensionName", ""),
        gender=_choice(Gender, payload.get("gender", "male"), "gender"),
        date_of_birth=_date(payload, "dateOfBirth"),
        is_american=payload.get("is_american") == "yes",
    )
    partner = None
    if payload.get("pensionTake_2"):
        partner = Person(
            name=payload.get("pensionName_2", ""),
            gender=_choice(Gender, payload.get("gender_2", "male"), "gender_2"),
            date_of_birth=_date(payload, "dateOfBirth_2"),
            is_american=payload.get("is_american_2") == "yes",
        )

    return Plan(
        person=person,
        partner=partner,
        base_problem=_choice(BaseProblem, payload.get("base_problem", "retire_asap"), "base_problem"),
        wanted_retire_age=_num(payload, "wanted_retire_age", None),
        max_retire_age=_req(payload, "base_problem_max_age", 60.0),
        max_cash_improvement=_req(payload, "base_problem_cash_improve"),
        max_risk_increase_pct=_req(payload, "base_problem_risk_increase"),
        retire_rule_confidence=_req(payload, "retireRule", 85.0),
        draw_keren_before_portfolio=payload.get("prati_hishtalmut_order") == "hishtalmut",
        cash_balance=_req(payload, "balance"),
        cash_buffer=_req(payload, "cashBuffer"),
        credit_limit=_req(payload, "creditLimit"),
        incomes=[
            _flow(payload, "income", i, "fire")
            for i in range(1, _count(payload, "num_income_fields", 1) + 1)
        ],
        expenses=[
            _flow(payload, "expense", i, "forever")
            for i in range(1, _count(payload, "num_expense_fields", 1) + 1)
        ],
        portfolios=[
            _portfolio(payload, i)
            for i in range(1, _count(payload, "num_portfolio_fields", 1) + 1)
        ],
        pension=_pension(payload, "", "pension_tactics", "pensionEndType1"),
        partner_pension=_pension(payload, "_2", "pension_tactics_2", "pensionEndType2"),
        kranot_hishtalmut=[
            KerenHishtalmut(
                balance=_req(payload, f"kerenBalance{i}"),
                monthly_deposit=_req(payload, f"kerenDeposit{i}"),
                annual_return_pct=_req(payload, f"kerenInterest{i}", 5.0),
                kind=_choice(KerenType, payload.get(f"kerenType{i}", "maslulit"), f"kerenType{i}"),
                annual_fee_pct=_req(payload, f"kerenFee{i}", 0.6),
                end_type=_choice(EndType, payload.get(f"kerenEndType{i}", "fire"), f"kerenEndType{i}"),
                end_date=_date(payload, f"kerenEndDate{i}"),
            )
            for i in range(1, _count(payload, "num_keren_fields") + 1)
        ],
        loans=[
            Loan(
                start_date=_date(payload, f"debtStartDate{i}"),
                annual_interest_pct=_req(payload, f"debtInterest{i}", 3.0),
                initial_sum=_req(payload, f"debtInitialSum{i}"),
                term_years=_req(payload, f"debtTotalPeriod{i}"),
                kind=_choice(LoanType, payload.get(f"debtType{i}", "spitzer"), f"debtType{i}"),
            )
            for i in range(1, _count(payload, "num_loan_fields") + 1)
        ],
        real_estate=[
            RealEstate(
                value=_req(payload, f"realestateValue{i}"),
                annual_rise_pct=_req(payload, f"realestateRise{i}"),
            )
            for i in range(1, _count(payload, "num_realestate_fields") + 1)
        ],
    )
