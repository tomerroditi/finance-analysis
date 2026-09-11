"""Input model for the early-retirement simulator.

Mirrors the input surface of the reference calculator this engine reproduces
(see ``research/zeke_retire_calc/notes/02-input-surface.md``). Everything is
expressed in **real terms** — today's shekels — so returns are real returns and
no inflation series is applied anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class StartType(str, Enum):
    """When a cash flow begins."""

    NOW = "now"
    FIRE = "fire"
    FROM_DATE = "from_date"
    ONE_TIME = "one_time"


class EndType(str, Enum):
    """When a cash flow stops."""

    FOREVER = "forever"
    FIRE = "fire"
    TO_DATE = "to_date"
    AGE_60 = "60"


class PortfolioDesignation(str, Enum):
    """What a portfolio is allowed to be used for."""

    WITHDRAW = "withdraw"
    GOAL = "goal"
    MUKERET_MAIN = "mukeret_main"
    MUKERET_PARTNER = "mukeret_partner"


GEMEL_ANNUAL_DEPOSIT_CEILING = 76_449.0
"""Statutory annual ceiling on gemel-le'hashkaa deposits, as the reference has
it — the 2023 figure, never updated. Recovered exactly from `pf_gemel_two`,
where the surplus splits as 200,000 - 20,000 - 167,258.5 = 12,741.50 across two
gemel accounts, i.e. 6,370.75 each. Applied **per account**, not per person."""

GEMEL_MONTHLY_DEPOSIT_CEILING = GEMEL_ANNUAL_DEPOSIT_CEILING / 12


class PortfolioType(str, Enum):
    """Investment instrument — drives tax treatment and deposit ceilings."""

    BROKER_IL = "portfolio"
    IBKR = "ibkr"
    GEMEL = "gemel"
    POLISA = "polisa"
    KASPIT = "kaspit"
    PIKADON = "pikadon"


class LotMethod(str, Enum):
    FLAT = "flat"
    FIFO = "fifo"
    LIFO = "lifo"


class KerenType(str, Enum):
    MASLULIT = "maslulit"
    IRA = "ira"


class LoanType(str, Enum):
    SPITZER = "spitzer"
    BALOON = "baloon"
    GRACE = "grace"


class PensionTactic(str, Enum):
    """When each annuity component starts being drawn."""

    ALL_FROM_60 = "60"
    ALL_FROM_STATUTORY = "67"
    MUKERET_60_ZAKA_STATUTORY = "60-67"


class BaseProblem(str, Enum):
    RETIRE_ASAP = "retire_asap"
    RETIRE_AT_AGE = "retire_at_age"
    IMPROVE_CASH = "improve_cash_to_reach_retire_at_age"
    INCREASE_RISK = "increase_risk_to_reach_retire_at_age"


@dataclass
class Person:
    name: str = ""
    gender: Gender = Gender.MALE
    date_of_birth: Optional[date] = None
    is_american: bool = False


@dataclass
class CashFlow:
    """A monthly income or expense stream."""

    amount: float = 0.0
    start_type: StartType = StartType.NOW
    start_date: Optional[date] = None
    end_type: EndType = EndType.FOREVER
    end_date: Optional[date] = None
    annual_rise_pct: float = 0.0
    description: str = ""


@dataclass
class Portfolio:
    """A taxed investment account."""

    balance: float = 0.0
    designation: PortfolioDesignation = PortfolioDesignation.WITHDRAW
    kind: PortfolioType = PortfolioType.BROKER_IL
    monthly_deposit_cap: Optional[float] = None
    goal: float = 0.0
    annual_return_pct: float = 5.0
    annual_fee_pct: float = 0.1
    profit_fraction_pct: float = 0.0
    lot_method: LotMethod = LotMethod.FLAT
    description: str = ""

    @property
    def effective_deposit_cap(self) -> float | None:
        """Monthly deposit ceiling, combining the user's cap and any statutory one."""
        caps = [c for c in (self.monthly_deposit_cap,
                            GEMEL_MONTHLY_DEPOSIT_CEILING
                            if self.kind == PortfolioType.GEMEL else None)
                if c is not None]
        return min(caps) if caps else None

    @property
    def monthly_factor(self) -> float:
        """Monthly growth factor.

        Verified against the reference to the shekel: the management fee is
        applied **multiplicatively**, not subtracted from the return.
        """
        return ((1 + self.annual_return_pct / 100) * (1 - self.annual_fee_pct / 100)) ** (1 / 12)


@dataclass
class Pension:
    balance: float = 0.0
    monthly_deposit: float = 0.0
    fee_on_balance_pct: float = 0.05
    fee_on_deposit_pct: float = 1.5
    annual_return_pct: float = 7.0
    tactic: PensionTactic = PensionTactic.ALL_FROM_60
    mukeret_pct: float = 30.0
    end_type: EndType = EndType.FIRE
    end_date: Optional[date] = None
    withdraw_severance: bool = False
    work_start_year: Optional[int] = None


@dataclass
class KerenHishtalmut:
    balance: float = 0.0
    monthly_deposit: float = 0.0
    annual_return_pct: float = 5.0
    kind: KerenType = KerenType.MASLULIT
    annual_fee_pct: float = 0.6
    end_type: EndType = EndType.FIRE
    end_date: Optional[date] = None


@dataclass
class Loan:
    start_date: Optional[date] = None
    annual_interest_pct: float = 3.0
    initial_sum: float = 0.0
    term_years: float = 0.0
    kind: LoanType = LoanType.SPITZER


@dataclass
class RealEstate:
    value: float = 0.0
    annual_rise_pct: float = 0.0


@dataclass
class Plan:
    """A complete scenario — the engine's single input."""

    person: Person = field(default_factory=Person)
    partner: Optional[Person] = None

    base_problem: BaseProblem = BaseProblem.RETIRE_ASAP
    wanted_retire_age: Optional[float] = None
    max_retire_age: float = 60.0
    max_cash_improvement: float = 0.0
    monthly_cash_improvement: float = 0.0
    """Extra monthly surplus the `improve_cash` solver assumes, up to
    `max_cash_improvement`. Applied while still working."""
    max_risk_increase_pct: float = 0.0

    retire_rule_confidence: float = 85.0
    decumulation_return_pct: float | None = None
    """Real return applied to withdrawal portfolios after retirement.

    The reference derives this from `retire_rule_confidence` and the length of
    the bridge to the state pension (a Trinity-style table — see
    notes/07-phase-model.md). That table has not been mapped yet, so this field
    lets a caller inject a known value; leaving it ``None`` falls back to zero,
    which is close for short bridges but wrong for long ones.
    """
    draw_keren_before_portfolio: bool = False

    cash_balance: float = 0.0
    cash_buffer: float = 0.0
    credit_limit: float = 0.0

    incomes: list[CashFlow] = field(default_factory=list)
    expenses: list[CashFlow] = field(default_factory=list)
    portfolios: list[Portfolio] = field(default_factory=list)
    pension: Optional[Pension] = None
    partner_pension: Optional[Pension] = None
    kranot_hishtalmut: list[KerenHishtalmut] = field(default_factory=list)
    loans: list[Loan] = field(default_factory=list)
    real_estate: list[RealEstate] = field(default_factory=list)
