"""Keren Hishtalmut (study fund) accounts.

Two behaviours distinguish these from taxable portfolios, both verified:

* **Fee**: a `maslulit` fund carries a hidden extra 0.6 pp on top of the stated
  management fee; an `ira` fund does not. Confirmed at stated fees of
  0.0 / 0.6 / 1.2 (notes/05).
* **Tax**: withdrawals are entirely tax-free — no tax series ever appears,
  unlike a taxable portfolio (notes/03).

Deposits are funded from **outside** the modelled surplus: adding a 2,000/month
deposit left the checking account still accruing the full 5,000 surplus while
the fund grew by 2,000 a month (`fixtures/kh_deposit`). That matches Israeli
practice, where the fund is funded from gross salary while the income the user
types is net.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.fire.models import KerenHishtalmut, KerenType

MASLULIT_HIDDEN_FEE_PCT = 0.6
"""Extra management fee a `maslulit` fund carries beyond the stated one."""


def effective_fee_pct(fund: KerenHishtalmut) -> float:
    if fund.kind == KerenType.MASLULIT:
        return fund.annual_fee_pct + MASLULIT_HIDDEN_FEE_PCT
    return fund.annual_fee_pct


def monthly_factor(fund: KerenHishtalmut) -> float:
    """Same multiplicative law as portfolios, on the effective fee."""
    return ((1 + fund.annual_return_pct / 100)
            * (1 - effective_fee_pct(fund) / 100)) ** (1 / 12)


@dataclass
class KerenAccount:
    """Runtime state of one study fund."""

    balance: float
    factor: float
    stated_fee_pct: float

    @classmethod
    def from_fund(cls, fund: KerenHishtalmut) -> "KerenAccount":
        return cls(balance=fund.balance, factor=monthly_factor(fund),
                   stated_fee_pct=fund.annual_fee_pct)

    def deposit(self, amount: float) -> None:
        self.balance += amount

    def decumulation_factor(self, decumulation_return_pct: float) -> float:
        """Post-retirement factor.

        Study funds take the same confidence-derived haircut as withdrawal
        portfolios once retired — verified on `pn_keren_maslulit`, where the
        fund's monthly factor drops from 1.003065 to 1.00095 at the retirement
        month while nothing else changes.

        Note the fee: a `maslulit` fund's hidden extra 0.6 pp applies only while
        accumulating. In decumulation only the **stated** fee is charged. Solving
        each of the four study-fund fixtures for the implied return recovers the
        decumulation table to within 0.09 pp under this rule, versus 0.7 pp if
        the hidden fee is kept.
        """
        return ((1 + decumulation_return_pct / 100)
                * (1 - self.stated_fee_pct / 100)) ** (1 / 12)

    def grow(self, factor: float | None = None) -> None:
        self.balance *= self.factor if factor is None else factor

    def withdraw_net(self, need: float) -> float:
        """Withdrawals are tax-free, so gross equals net."""
        take = min(need, self.balance)
        self.balance -= take
        return take
