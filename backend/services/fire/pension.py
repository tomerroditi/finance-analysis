"""Israeli pension fund: accumulation, annuitisation and the tax on the annuity.

All of this is pinned to the reference's behaviour (notes/05).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.fire import israeli_tax
from backend.services.fire.models import Gender, Pension, PensionTactic
from backend.services.fire.severance import SeveranceRedemption, redeem

ANNUITY_FACTORS: dict[Gender, dict[int, float]] = {
    Gender.MALE: {60: 224.41736, 67: 197.82330},
    Gender.FEMALE: {60: 227.34593, 65: 209.71688},
}
"""Divisor turning an accrued balance into a monthly annuity (מקדם קצבה).

Recovered by dividing the balance at annuitisation by the annuity the reference
reports. Precision is limited by that report carrying one decimal, so each
figure is good to roughly ±0.0005 — the male values come from the largest
available balances (6.0M and 6.5M), where the relative rounding error is
smallest.

Only the two claim ages the UI can request are known per gender; the curve
between them is unmapped, and the genders do not share a table (notes/05)."""

TAGMULIM_SHARE = 0.6
"""Hard-coded split of each component into employee contributions vs severance;
it does not move with `percentage_mukeret`."""

BL_CONTRIBUTION_THRESHOLD = 7_703.4
BL_CONTRIBUTION_LOW_RATE = 0.0425
BL_CONTRIBUTION_HIGH_RATE = 0.1190
"""National-insurance contributions levied on an annuity drawn *before* the
statutory pension age, on the whole annuity including the recognised part."""


def annuity_factor(gender: Gender, claim_age: int) -> float:
    try:
        return ANNUITY_FACTORS[gender][claim_age]
    except KeyError as exc:
        raise NotImplementedError(
            f"annuity factor for {gender.value} at {claim_age} is not known — "
            "only the claim ages the reference exposes have been measured"
        ) from exc


def contributions_on(annuity: float) -> float:
    """Bituach Leumi contributions on an annuity drawn before statutory age."""
    if annuity <= 0:
        return 0.0
    low = min(annuity, BL_CONTRIBUTION_THRESHOLD) * BL_CONTRIBUTION_LOW_RATE
    high = max(annuity - BL_CONTRIBUTION_THRESHOLD, 0.0) * BL_CONTRIBUTION_HIGH_RATE
    return low + high


@dataclass
class AnnuityStream:
    """One annuity component, from the age it starts being drawn."""

    monthly: float
    start_age: float
    recognised: bool
    """Recognised (מוכרת) annuity is income-tax free; entitling (מזכה) is not."""

    component: str = "tagmulim"
    """`tagmulim` (contributions) or `pitzuim` (severance). The reference lists
    the four combinations of this with `recognised` separately, and the split
    between them is a fixed 60/40 (notes/05)."""

    claim_age: int = 0
    factor: float = 0.0
    """The claim age, and the annuity factor the reference prints beside it."""


@dataclass
class PensionAccount:
    """Runtime state of one pension fund."""

    plan_pension: Pension
    gender: Gender
    statutory_age: int
    balance: float = 0.0
    streams: list[AnnuityStream] = field(default_factory=list)
    annuitised: set[int] = field(default_factory=set)
    severance: SeveranceRedemption | None = None
    severance_start_month: int | None = None
    recognised_share: float | None = None
    """Recognised share of the balance, once a severance redemption has moved it."""

    def __post_init__(self):
        self.balance = self.plan_pension.balance

    @property
    def monthly_factor(self) -> float:
        return ((1 + self.plan_pension.annual_return_pct / 100)
                * (1 - self.plan_pension.fee_on_balance_pct / 100)) ** (1 / 12)

    def contribute(self) -> None:
        """A monthly deposit, net of the fee charged on the deposit itself."""
        self.balance += self.plan_pension.monthly_deposit * (
            1 - self.plan_pension.fee_on_deposit_pct / 100)

    def grow(self) -> None:
        self.balance *= self.monthly_factor

    def redeem_severance(self, year: int, month_index: int) -> float:
        """Cash out the entitling employer severance. Returns the gross paid.

        The redeemed component leaves the pension, so the annuity that would
        have been paid on it disappears; the tax is billed separately over a
        spread (notes/05).

        Only the *entitling* side shrinks. The recognised annuity is still
        `mukeret_pct` of the balance the fund had **before** the redemption, so
        its share of what is left grows — verified in `pn_pizuim_2010`, where
        the reference pays 1,819.8 recognised against 1,310.3 if the percentage
        were re-applied to the reduced balance (notes/16).
        """
        if self.severance is not None:
            return 0.0
        before = self.balance
        self.severance = redeem(before, self.plan_pension.mukeret_pct,
                                year, self.plan_pension.work_start_year)
        self.severance_start_month = month_index
        self.balance -= self.severance.gross
        if self.balance > 0:
            self.recognised_share = (self.plan_pension.mukeret_pct / 100) * before / self.balance
        return self.severance.gross

    def _claim(self, share: float, claim_age: int, recognised: bool, age: float) -> None:
        """Convert `share` of the balance, as the two components the reference lists.

        Each claim splits 60/40 into contributions and severance. The one
        exception is the entitling side after a severance redemption: that
        component has left the fund, so what is annuitised is all
        contributions — `pn_pizuim_2010` lists exactly three pension rows, not
        four (notes/16).
        """
        amount = self.balance * share
        if amount <= 0:
            return
        factor = annuity_factor(self.gender, claim_age)
        redeemed = self.severance is not None and not recognised
        splits = ({"tagmulim": 1.0} if redeemed
                  else {"tagmulim": TAGMULIM_SHARE, "pitzuim": 1 - TAGMULIM_SHARE})
        for component, part in splits.items():
            self.streams.append(AnnuityStream(
                monthly=amount * part / factor, recognised=recognised,
                start_age=age, component=component, claim_age=claim_age,
                factor=factor))

    def annuitise_due(self, age: float) -> None:
        """Convert whatever is due at this age into annuity streams.

        `pension_tactics` decides what converts when: everything at 60,
        everything at the statutory age, or the recognised share at 60 and the
        entitling share at the statutory age (notes/05).
        """
        mukeret = (self.recognised_share if self.recognised_share is not None
                   else self.plan_pension.mukeret_pct / 100)
        tactic = self.plan_pension.tactic

        def due(claim_age: int) -> bool:
            return claim_age not in self.annuitised and age > claim_age

        if tactic == PensionTactic.ALL_FROM_60 and due(60):
            self._claim(mukeret, 60, True, age)
            self._claim(1 - mukeret, 60, False, age)
            self.annuitised.add(60)
            self.balance = 0.0
        elif tactic == PensionTactic.ALL_FROM_STATUTORY and due(self.statutory_age):
            self._claim(mukeret, self.statutory_age, True, age)
            self._claim(1 - mukeret, self.statutory_age, False, age)
            self.annuitised.add(self.statutory_age)
            self.balance = 0.0
        elif tactic == PensionTactic.MUKERET_60_ZAKA_STATUTORY:
            if due(60):
                self._claim(mukeret, 60, True, age)
                self.balance *= 1 - mukeret
                self.annuitised.add(60)
            if due(self.statutory_age):
                self._claim(1.0, self.statutory_age, False, age)
                self.balance = 0.0
                self.annuitised.add(self.statutory_age)

    def income_at(self, age: float) -> tuple[float, float]:
        """`(recognised, entitling)` annuity being drawn at `age`."""
        recognised = sum(s.monthly for s in self.streams if s.recognised and age >= s.start_age)
        entitling = sum(s.monthly for s in self.streams if not s.recognised and age >= s.start_age)
        return recognised, entitling

    def deductions_at(self, age: float, month_index: int | None = None,
                      also_drawing: float = 0.0) -> tuple[float, float]:
        """`(income_tax, national_insurance)` on the annuity at `age`.

        `also_drawing` is recognised annuity this person draws from outside the
        pension fund — a gemel converted at 60. It is tax-free like any
        recognised annuity, but national insurance is charged on the **whole**
        annuity a person draws before their statutory age, so it belongs in that
        base (notes/16: leaving it out cost `pf_mukeret2` 1,103.9 a month).
        """
        recognised, entitling = self.income_at(age)
        recognised += also_drawing
        exemption = (israeli_tax.STATUTORY_AGE_MONTHLY_EXEMPTION
                     if age > self.statutory_age else 0.0)
        if self.severance is not None:
            # Taking severance exempt permanently shrinks the pension exemption.
            exemption = max(exemption - self.severance.exemption_offset, 0.0)
        tax = israeli_tax.monthly_income_tax(entitling, exemption)
        insurance = (0.0 if age > self.statutory_age
                     else contributions_on(recognised + entitling))
        return tax + self.severance_tax_at(month_index), insurance

    def severance_tax_at(self, month_index: int | None) -> float:
        """Monthly tax on the spread portion of a severance redemption."""
        if self.severance is None or self.severance_start_month is None:
            return 0.0
        if month_index is None:
            return 0.0
        elapsed = month_index - self.severance_start_month
        if 0 <= elapsed < self.severance.spread_months:
            return self.severance.monthly_tax
        return 0.0
