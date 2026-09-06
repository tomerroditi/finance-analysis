"""FIFO / LIFO lot accounting for taxable portfolios.

The reference has no real purchase history to work from — the user supplies a
balance and a profit fraction — so it manufactures one: the opening balance is
treated as a run of **equal-basis monthly purchases**, the newest bought *last*
month and the oldest `N` months ago, each grown at the portfolio's own rate
since. `N` is whatever makes today's profit fraction come out at the number
typed:

```
sum(f**a for a in range(1, N + 1)) == N / (1 - profit_fraction)
```

A 5% portfolio at 50% profit gives 315 lots (26 years); at 90% profit, 907
(76 years). That is why FIFO starts with a very high taxable share and LIFO
with almost none. Later deposits simply append lots bought at par.

Where the ladder *starts* is unobservable: the lots are rescaled to the stated
balance, and shifting every age by a constant is exactly undone by that
rescale. What the sale prices do see is `N`, and the sum above is the version
that fits — running it from `a = 0` instead gives one lot more (316 and 908),
and doubles the worst tax disagreement on every fixture that has a synthetic
history at all.

Verified by replaying the reference's own withdrawals through this model across
seven scenarios (FIFO and LIFO, with and without deposits, 50% and 90% profit,
and two with a *known* deposit history and no synthetic part at all): the
worst monthly tax disagreement is between 0.05 and 1.83 shekels.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.fire.models import LotMethod


@dataclass
class Lot:
    """One purchase: what it cost, and what it is worth now."""

    basis: float
    value: float

    @property
    def gain_fraction(self) -> float:
        if self.value <= 0:
            return 0.0
        return max(self.value - self.basis, 0.0) / self.value


def solve_lot_count(monthly_factor: float, profit_fraction: float) -> int:
    """Number of synthetic monthly purchases implied by a profit fraction.

    A portfolio that does not grow has no history to manufacture: without
    growth every lot would be identical, so the profit fraction cannot be
    produced by ageing purchases at all. One lot carrying the whole embedded
    gain is then the only consistent answer — and the right one, since FIFO,
    LIFO and a flat basis are indistinguishable on identical lots.

    A balance declared 100% profit is the same degenerate case from the other
    end: it would need infinitely many lots of zero basis, which is one lot of
    zero basis.
    """
    if profit_fraction <= 0 or profit_fraction >= 1 or monthly_factor <= 1:
        return 1
    f = monthly_factor
    low, high = 1.0, 4000.0
    for _ in range(200):
        mid = (low + high) / 2
        if f * (f ** mid - 1) / (f - 1) < mid / (1 - profit_fraction):
            low = mid
        else:
            high = mid
    return max(int(round((low + high) / 2)), 1)


def opening_lots(balance: float, profit_fraction: float,
                 monthly_factor: float) -> list[Lot]:
    """Expand an opening balance into its synthetic purchase history.

    Returned oldest-first, so FIFO consumes from the front and LIFO the back.
    """
    if balance <= 0:
        return []
    if profit_fraction <= 0:
        return [Lot(basis=balance, value=balance)]

    count = solve_lot_count(monthly_factor, profit_fraction)
    if count == 1:
        return [Lot(basis=balance * (1 - profit_fraction), value=balance)]
    per_lot = balance * (1 - profit_fraction) / count
    lots = [Lot(basis=per_lot, value=per_lot * monthly_factor ** age)
            for age in reversed(range(1, count + 1))]
    # `count` is a rounded solution of a continuous equation, so rescale to hit
    # the stated balance exactly.
    total = sum(lot.value for lot in lots)
    scale = balance / total
    for lot in lots:
        lot.value *= scale
    return lots


def realised_gain(lots: list[Lot], method: LotMethod, gross: float,
                  commit: bool = True) -> float:
    """Gain realised by selling `gross`, oldest- or newest-first.

    With `commit=False` the pool is left untouched, which is what the tax
    gross-up needs while it searches.
    """
    if gross <= 0 or not lots:
        return 0.0
    order = (range(len(lots)) if method is LotMethod.FIFO
             else range(len(lots) - 1, -1, -1))
    remaining = gross
    realised = 0.0
    emptied: list[int] = []
    for index in order:
        if remaining <= 1e-9:
            break
        lot = lots[index]
        if lot.value <= 0:
            continue
        take = min(remaining, lot.value)
        realised += take * lot.gain_fraction
        remaining -= take
        if commit:
            lot.basis -= lot.basis * take / lot.value
            lot.value -= take
            if lot.value <= 1e-9:
                emptied.append(index)
    for index in sorted(emptied, reverse=True):
        lots.pop(index)
    return realised
