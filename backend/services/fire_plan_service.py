"""The user's early-retirement plan, filled from and kept in step with tracked data.

The calculator (`backend/services/fire/`) takes the reference's flat form. This
service owns the one form the user keeps: it saves it, and it fills it from
what the app already tracks — cash, investments, keren hishtalmut, pension
funds, loans, and the household's typical spending and income.

Two kinds of field follow tracked data:

* **linked scalars** — single-value fields named in the plan's `linked` list
  (the cash balance, the pension balance and deposit, its fees). They are
  overwritten from tracked data on every read until the user edits one, which
  drops it from the list.
* **sourced rows** — a row of a repeatable section whose hidden `*Source`
  field names a tracked account (`investment:12`, `liability:3`,
  `tracked:expenses`). Its tracked fields are refreshed on every read; a row
  whose account no longer exists (closed, paid off, deleted) is dropped, since
  its money is no longer there.

Everything else is the user's own assumption — returns, fees they typed, the
retirement problem — and is never touched. Until a plan is saved, one is
derived on the fly, seeded from the old retirement goal where there is one
(its age, gender, target age and spending), so a user of the previous
calculator lands on their own numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.fire_scenario_repository import FireScenarioRepository
from backend.repositories.retirement_goal_repository import RetirementGoalRepository
from backend.services.analysis import AnalysisService
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService
from backend.services.insurance_account_service import InsuranceAccountService
from backend.services.investments import InvestmentsService
from backend.services.liabilities_service import LiabilitiesService

KEREN_TYPE = "hishtalmut"
PENSION_TYPE = "pension"
REAL_ESTATE_TYPE = "real_estate"

ROW_STEMS: dict[str, tuple[str, ...]] = {
    "expense": (
        "expenseStartType",
        "expenseStartDate",
        "expenseEndType",
        "expenseEndDate",
        "expenseSum",
        "expenseRise",
        "expenseDescription",
        "expenseSource",
    ),
    "income": (
        "incomeStartType",
        "incomeStartDate",
        "incomeEndType",
        "incomeEndDate",
        "incomeSum",
        "incomeRise",
        "incomeDescription",
        "incomeSource",
    ),
    "portfolio": (
        "portfolioDesignation",
        "portfolio_type",
        "portfolioBalance",
        "portfolio_deposit",
        "portfolio_goal",
        "portfolioInterest",
        "portfolioFee",
        "portfolioProfitFraction",
        "portfolio_fifo_lifo",
        "portfolioDescription",
        "portfolioSource",
    ),
    "keren": (
        "kerenBalance",
        "kerenDeposit",
        "kerenInterest",
        "kerenType",
        "kerenFee",
        "kerenEndType",
        "kerenEndDate",
        "kerenSource",
    ),
    "loan": (
        "debtStartDate",
        "debtInterest",
        "debtInitialSum",
        "debtTotalPeriod",
        "debtType",
        "debtSource",
    ),
    "realestate": ("realestateValue", "realestateRise", "realestateSource"),
}
"""Per-row field stems of each repeatable section, as in the form's schema
(`frontend/src/components/fire/schema.ts`). A row's field is the stem plus its
1-based index; the last stem of each is the hidden source field."""

SOURCE_STEM = {section: stems[-1] for section, stems in ROW_STEMS.items()}

AMORTIZATION_TO_LOAN_TYPE = {"shpitzer": "spitzer", "balloon": "baloon"}
"""Liability amortisation method -> the calculator's loan type. Equal-principal
has no counterpart; it is modelled as Spitzer, the same term and rate."""


def _fmt(value: float) -> str:
    """Write a number as the form does: two decimals at most, no trailing zeros."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


@dataclass
class TrackedRow:
    """A tracked account the plan can hold as a row of its own.

    `fields` follow the account on every read; `seed` is only written when the
    row is first added, and is the user's to change after that.
    """

    source: str
    label: str
    fields: dict[str, str]
    seed: dict[str, str] = field(default_factory=dict)


@dataclass
class Tracked:
    """What the user's data says, in the calculator's own field names."""

    scalars: dict[str, str]
    rows: dict[str, list[TrackedRow]]

    def row(self, section: str, source: str) -> TrackedRow | None:
        """Find the tracked row of `section` named `source`, if it still exists."""
        return next((r for r in self.rows.get(section, []) if r.source == source), None)


class FirePlanService:
    """Load, derive and save the user's early-retirement plan.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.repo = FireScenarioRepository(db)
        self.goal_repo = RetirementGoalRepository(db)
        self.analysis = AnalysisService(db)
        self.bank_balances = BankBalanceService(db)
        self.cash_balances = CashBalanceService(db)
        self.insurance = InsuranceAccountService(db)
        self.investments = InvestmentsService(db)
        self.liabilities = LiabilitiesService(db)

    # -- public API -----------------------------------------------------------

    def get_plan(self) -> dict[str, Any]:
        """Return the plan for the form: saved and refreshed, or derived from tracked data.

        Returns
        -------
        dict
            ``saved`` (whether the user has saved one), ``fields`` (the flat
            form), ``linked`` (scalars following tracked data) and ``tracked``
            (what tracked data says, so the form can re-link a field or add an
            account it does not hold yet).
        """
        tracked = self.tracked()
        stored = self.repo.get()
        if stored is None:
            fields, linked = self._derive(tracked)
        else:
            linked = json.loads(stored.linked or "[]")
            fields = self._refresh(json.loads(stored.fields), linked, tracked)
        return {
            "saved": stored is not None,
            "fields": fields,
            "linked": linked,
            "tracked": {
                "scalars": tracked.scalars,
                "rows": {
                    section: [row.__dict__ for row in rows]
                    for section, rows in tracked.rows.items()
                },
            },
        }

    def save_plan(self, fields: dict[str, str], linked: list[str]) -> dict[str, Any]:
        """Save the plan and return it as `get_plan` would."""
        self.repo.upsert(json.dumps(fields), json.dumps(sorted(set(linked))))
        return self.get_plan()

    def reset_plan(self) -> dict[str, Any]:
        """Forget the saved plan; return the one derived from tracked data."""
        self.repo.delete()
        return self.get_plan()

    def runnable_fields(self) -> dict[str, str] | None:
        """Return the plan's fields, or None while it lacks the date of birth it needs."""
        fields = self.get_plan()["fields"]
        return fields if fields.get("dateOfBirth") else None

    # -- tracked data ---------------------------------------------------------

    def tracked(self) -> Tracked:
        """Read everything the plan can follow from tracked data."""
        scalars = {"balance": _fmt(self._cash())}
        scalars.update(self._pension())
        income, expenses = self._typical_month()
        return Tracked(
            scalars=scalars,
            rows={
                "expense": self._flow_rows("expense", expenses),
                "income": self._flow_rows("income", income),
                "portfolio": self._portfolio_rows(),
                "keren": self._keren_rows(),
                "loan": self._loan_rows(),
                "realestate": self._real_estate_rows(),
            },
        )

    def _cash(self) -> float:
        """Bank and cash balances, summed."""
        return sum(
            float(row["balance"] or 0.0)
            for row in (
                *self.bank_balances.get_all_balances(),
                *self.cash_balances.get_all_balances(),
            )
        )

    def _typical_month(self) -> tuple[float, float]:
        """`(income, expenses)` of a typical month, as the old calculator read them.

        Complete months only, and the median rather than the mean on both
        sides — 6 months of income, 12 of expenses — so one windfall or one
        wedding does not become the plan (see `retirement_calculations.md`).
        """
        months = self.analysis.get_income_expenses_over_time()
        if not months:
            return 0.0, 0.0
        running = pd.Timestamp.today().strftime("%Y-%m")
        complete = [m for m in months if m["month"] < running] or months
        income = float(pd.Series([m["income"] for m in complete[-6:]]).median())
        expenses = float(pd.Series([m["expenses"] for m in complete[-12:]]).median())
        return income, expenses

    @staticmethod
    def _flow_rows(side: str, amount: float) -> list[TrackedRow]:
        """Express the household's typical spending or income as one row."""
        if amount <= 0:
            return []
        return [
            TrackedRow(
                source=f"tracked:{side}",
                label=side,
                fields={f"{side}Sum": _fmt(amount)},
                seed={
                    f"{side}StartType": "now",
                    f"{side}EndType": "fire" if side == "income" else "forever",
                    f"{side}Rise": "0.0",
                },
            )
        ]

    def _open_investments(self) -> list[dict[str, Any]]:
        return self.investments.get_all_investments(include_closed=False)

    def _portfolio_rows(self) -> list[TrackedRow]:
        """One row per open investment that is not a fund the plan models apart."""
        rows = []
        for investment in self._open_investments():
            if investment["type"] in (KEREN_TYPE, PENSION_TYPE, REAL_ESTATE_TYPE):
                continue
            result = self.investments.calculate_profit_loss(investment["id"])
            balance = float(result["current_balance"])
            if balance <= 0:
                continue
            gain = max(balance - float(result["net_invested"]), 0.0)
            seed = {
                "portfolioDesignation": "withdraw",
                "portfolio_type": "portfolio",
                "portfolioInterest": "5.0",
                "portfolio_fifo_lifo": "flat",
                "portfolioDescription": investment["name"],
            }
            fee = investment.get("commission_management")
            seed["portfolioFee"] = _fmt(fee) if fee is not None else "0.1"
            rows.append(
                TrackedRow(
                    source=f"investment:{investment['id']}",
                    label=investment["name"],
                    fields={
                        "portfolioBalance": _fmt(balance),
                        "portfolioProfitFraction": _fmt(100 * gain / balance),
                    },
                    seed=seed,
                )
            )
        return rows

    def _keren_rows(self) -> list[TrackedRow]:
        """One row per open keren hishtalmut, with its own deposit and fee."""
        deposits = self.insurance.get_monthly_contributions(KEREN_TYPE)
        policies = {a.policy_id: a for a in self.insurance.get_all()}
        rows = []
        for investment in self._open_investments():
            if investment["type"] != KEREN_TYPE:
                continue
            balance = self.investments.calculate_current_balance(investment["id"])
            policy = policies.get(investment.get("insurance_policy_id") or "")
            deposit = deposits.get(policy.policy_id, 0.0) if policy else 0.0
            fee = policy.commission_savings_pct if policy else None
            rows.append(
                TrackedRow(
                    source=f"investment:{investment['id']}",
                    label=investment["name"],
                    fields={
                        "kerenBalance": _fmt(balance),
                        "kerenDeposit": _fmt(deposit),
                    },
                    seed={
                        "kerenInterest": "5.0",
                        "kerenType": "maslulit",
                        "kerenFee": _fmt(fee) if fee is not None else "0.6",
                        "kerenEndType": "fire",
                    },
                )
            )
        return rows

    def _pension(self) -> dict[str, str]:
        """Sum the pension funds into the calculator's single fund.

        Fees are balance-weighted across funds. A pension typed by hand as an
        investment is added to the balance; the scraped funds are not
        investments, so nothing is counted twice.
        """
        funds = [a for a in self.insurance.get_all() if a.policy_type == PENSION_TYPE]
        manual = sum(
            self.investments.calculate_current_balance(i["id"])
            for i in self._open_investments()
            if i["type"] == PENSION_TYPE
        )
        balance = sum(float(f.balance or 0.0) for f in funds) + manual
        if not funds and not manual:
            return {}
        scalars = {
            "pensionBalance": _fmt(balance),
            "pensionDeposit": _fmt(
                sum(self.insurance.get_monthly_contributions(PENSION_TYPE).values())
            ),
        }
        for key, column in (
            ("pensionFee1", "commission_savings_pct"),
            ("pensionFee2", "commission_deposits_pct"),
        ):
            weighted = [
                (float(f.balance or 0.0), getattr(f, column))
                for f in funds
                if getattr(f, column) is not None
            ]
            total = sum(weight for weight, _ in weighted)
            if total > 0:
                scalars[key] = _fmt(sum(w * fee for w, fee in weighted) / total)
        return scalars

    def _loan_rows(self) -> list[TrackedRow]:
        """One row per active liability."""
        rows = []
        for loan in self.liabilities.get_all_liabilities(include_paid_off=False):
            rate = loan.get("current_rate")
            rows.append(
                TrackedRow(
                    source=f"liability:{loan['id']}",
                    label=loan["name"],
                    fields={
                        "debtStartDate": str(loan["start_date"])[:10],
                        "debtInterest": _fmt(
                            rate if rate is not None else loan["interest_rate"]
                        ),
                        "debtInitialSum": _fmt(loan["principal_amount"]),
                        "debtTotalPeriod": _fmt(loan["term_months"] / 12),
                        "debtType": AMORTIZATION_TO_LOAN_TYPE.get(
                            loan.get("amortization_method") or "", "spitzer"
                        ),
                    },
                )
            )
        return rows

    def _real_estate_rows(self) -> list[TrackedRow]:
        """One row per open real-estate investment."""
        return [
            TrackedRow(
                source=f"investment:{investment['id']}",
                label=investment["name"],
                fields={
                    "realestateValue": _fmt(
                        self.investments.calculate_current_balance(investment["id"])
                    )
                },
                seed={"realestateRise": "0.0"},
            )
            for investment in self._open_investments()
            if investment["type"] == REAL_ESTATE_TYPE
        ]

    # -- composing the form ---------------------------------------------------

    @staticmethod
    def _rows(fields: dict[str, str], section: str) -> list[dict[str, str]]:
        """Read a section's rows, each keyed by stem."""
        count = int(fields.get(f"num_{section}_fields") or 0)
        return [
            {
                stem: fields[f"{stem}{i}"]
                for stem in ROW_STEMS[section]
                if f"{stem}{i}" in fields
            }
            for i in range(1, count + 1)
        ]

    @staticmethod
    def _write_rows(
        fields: dict[str, str], section: str, rows: list[dict[str, str]]
    ) -> None:
        """Replace a section's rows in `fields`."""
        old = int(fields.get(f"num_{section}_fields") or 0)
        for i in range(1, max(old, len(rows)) + 1):
            for stem in ROW_STEMS[section]:
                fields.pop(f"{stem}{i}", None)
        for i, row in enumerate(rows, start=1):
            for stem, value in row.items():
                fields[f"{stem}{i}"] = value
        fields[f"num_{section}_fields"] = str(len(rows))

    def _refresh(
        self, fields: dict[str, str], linked: list[str], tracked: Tracked
    ) -> dict[str, str]:
        """Overwrite linked scalars and sourced rows with what tracked data says now."""
        fields = dict(fields)
        for name in linked:
            if name in tracked.scalars:
                fields[name] = tracked.scalars[name]
        for section in ROW_STEMS:
            rows = []
            for row in self._rows(fields, section):
                source = row.get(SOURCE_STEM[section])
                if source:
                    current = tracked.row(section, source)
                    if current is None:
                        continue
                    row.update(current.fields)
                rows.append(row)
            if rows or f"num_{section}_fields" in fields:
                self._write_rows(fields, section, rows)
        return fields

    def _derive(self, tracked: Tracked) -> tuple[dict[str, str], list[str]]:
        """Derive a first plan from tracked data, seeded from the old retirement goal."""
        fields: dict[str, str] = {
            "base_problem": "retire_asap",
            "base_problem_max_age": "60",
        }
        fields.update(tracked.scalars)
        linked = sorted(tracked.scalars)

        for section, rows in tracked.rows.items():
            self._write_rows(
                fields,
                section,
                [
                    {**row.seed, **row.fields, SOURCE_STEM[section]: row.source}
                    for row in rows
                ],
            )

        goal = self.goal_repo.get()
        if goal is not None:
            today = date.today()
            fields["gender"] = goal.gender
            fields["dateOfBirth"] = date(
                today.year - goal.current_age, today.month, 1
            ).isoformat()
            fields["base_problem_max_age"] = str(goal.target_retirement_age)
            self._seed_spending(fields, goal)
        return fields, linked

    def _seed_spending(self, fields: dict[str, str], goal: Any) -> None:
        """Carry the old goal's spending over: today's, then the retirement budget.

        The old calculator took a spending override for today and a separate
        budget for retirement. The new one says the same with two rows: today's
        spending until retirement, the retirement budget from then on.
        """
        rows = self._rows(fields, "expense")
        if goal.monthly_expenses_override is not None:
            rows = [
                {
                    "expenseStartType": "now",
                    "expenseEndType": "forever",
                    "expenseSum": _fmt(goal.monthly_expenses_override),
                    "expenseRise": "0.0",
                }
            ]
        if goal.monthly_expenses_in_retirement and rows:
            rows[0]["expenseEndType"] = "fire"
            rows.append(
                {
                    "expenseStartType": "fire",
                    "expenseEndType": "forever",
                    "expenseSum": _fmt(goal.monthly_expenses_in_retirement),
                    "expenseRise": "0.0",
                }
            )
        self._write_rows(fields, "expense", rows)
