"""Capital-gains tax on portfolio withdrawals.

Israeli CGT is 25% on real gains, and the reference applies it by grossing the
withdrawal up: to spend `need` net you must sell enough that what remains after
tax equals `need`.

The `flat` lot method — the reference's default — treats every shekel of the
balance as the same blend of principal and gain:

```
g = (balance - basis) / balance          # unrealised gain fraction
W = need / (1 - rate * g)                # gross sale, capped at the balance
tax = W * rate * g
basis -= W * (1 - g)                     # basis is consumed proportionally
balance -= W
```

Verified to 0.1 against `fixtures/cf_credit_0`, across 26 consecutive months
including the final partial withdrawal that leaves a shortfall.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.fire import israeli_tax
from backend.services.fire import lots as lot_math
from backend.services.fire.models import LotMethod, Portfolio

CAPITAL_GAINS_RATE = israeli_tax.CAPITAL_GAINS_FLAT_RATE
"""Israeli CGT on securities. Confirmed by fitting `cf_credit_0` exactly."""


@dataclass
class TaxableAccount:
    """A portfolio balance together with its cost basis.

    Under the `flat` method the basis is a single pooled number. Under FIFO or
    LIFO the account also carries an explicit lot list, since which lots a sale
    consumes decides how much of it is taxable (lots.py).
    """

    balance: float
    basis: float
    method: LotMethod = LotMethod.FLAT
    lots: list[lot_math.Lot] = field(default_factory=list)

    @classmethod
    def from_portfolio(cls, portfolio: Portfolio) -> "TaxableAccount":
        """Opening state — `profit_fraction_pct` sets how much is already gain."""
        gain = portfolio.balance * portfolio.profit_fraction_pct / 100
        return cls(
            balance=portfolio.balance,
            basis=portfolio.balance - gain,
            method=portfolio.lot_method,
            lots=(lot_math.opening_lots(portfolio.balance,
                                        portfolio.profit_fraction_pct / 100,
                                        portfolio.monthly_factor)
                  if portfolio.lot_method is not LotMethod.FLAT else []),
        )

    @property
    def gain_fraction(self) -> float:
        if self.balance <= 0:
            return 0.0
        return max(self.balance - self.basis, 0.0) / self.balance

    def deposit(self, amount: float) -> None:
        """A deposit adds to both balance and basis, and buys a lot at par."""
        if amount <= 0:
            return
        self.balance += amount
        self.basis += amount
        if self.method is not LotMethod.FLAT:
            self.lots.append(lot_math.Lot(basis=amount, value=amount))

    def grow(self, factor: float) -> None:
        """Growth lifts values only — the extra is unrealised gain."""
        self.balance *= factor
        for lot in self.lots:
            lot.value *= factor

    def withdraw_net(self, need: float, age: float = 0.0,
                     statutory_age: int = 67) -> tuple[float, float]:
        """Sell enough to net `need`. Returns `(net_received, tax_paid)`.

        Below 60 the tax is a flat share of the realised gain, so the gross-up
        is closed form: pooled under `flat`, and a walk down the lot ladder
        under FIFO or LIFO (lots.py). From 60 the gain is taxed on the
        progressive brackets instead, which no longer decomposes lot by lot, so
        the gross-up is solved numerically — the tax is monotone in the gross,
        which makes bisection safe.
        """
        if self.balance <= 0 or need <= 0:
            return 0.0, 0.0

        gain_share = self.gain_fraction

        def gain_on(gross: float) -> float:
            if self.method is LotMethod.FLAT:
                return gross * gain_share
            return lot_math.realised_gain(self.lots, self.method, gross, commit=False)

        def tax_on(gross: float) -> float:
            return israeli_tax.capital_gains_tax(gain_on(gross), age, statutory_age)

        ceiling = need / max(1 - CAPITAL_GAINS_RATE * gain_share, 1e-9)
        if age <= israeli_tax.MARGINAL_TREATMENT_AGE:
            gross = (ceiling if self.method is LotMethod.FLAT
                     else lot_math.gross_for_net(self.lots, self.method, need,
                                                 CAPITAL_GAINS_RATE))
        else:
            ceiling = max(ceiling, need / max(1 - CAPITAL_GAINS_RATE, 1e-9))
            low, high = need, ceiling
            for _ in range(60):
                mid = (low + high) / 2
                if mid - tax_on(mid) < need:
                    low = mid
                else:
                    high = mid
            gross = (low + high) / 2

        gross = min(gross, self.balance)
        if self.method is LotMethod.FLAT:
            tax = tax_on(gross)
            self.basis -= gross * (1 - gain_share)
        else:
            realised = lot_math.realised_gain(self.lots, self.method, gross)
            tax = israeli_tax.capital_gains_tax(realised, age, statutory_age)
            self.basis = sum(lot.basis for lot in self.lots)
        self.balance -= gross
        return gross - tax, tax
