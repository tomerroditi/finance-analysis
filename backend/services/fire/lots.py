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

`N` is the continuous solution **rounded down** to whole months, and the
history is then scaled — basis and value alike — to the stated balance, so the
profit fraction it actually carries lands slightly above the one typed rather
than being forced onto it. `lots2` read this lot by lot: one portfolio sold
newest- or oldest-first every month from retirement, at 20-90% profit, 3-8%
return, with a fee, and at three times the size. The month's tax over its sale
is the gain fraction of exactly the lots sold, and every variant of the
construction was replayed against eighteen lot fixtures: rounding down and
scaling both leaves a worst gap of 28 shekels on 8-24M portfolios, where
rounding to nearest and forcing the typed fraction (the previous model) left
1,323. Running the sum from `a = 0`, ceiling, or a fractional oldest lot are
all worse.
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
        """Share of the lot's current value that is unrealised gain."""
        if self.value <= 0:
            return 0.0
        return max(self.value - self.basis, 0.0) / self.value


def solve_lot_count(monthly_factor: float, profit_fraction: float) -> int:
    """Count the synthetic monthly purchases implied by a profit fraction.

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
        if f * (f**mid - 1) / (f - 1) < mid / (1 - profit_fraction):
            low = mid
        else:
            high = mid
    return max(int((low + high) / 2), 1)


def opening_lots(
    balance: float, profit_fraction: float, monthly_factor: float
) -> list[Lot]:
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
    lots = [
        Lot(basis=1.0, value=monthly_factor**age)
        for age in reversed(range(1, count + 1))
    ]
    # Whole lots only, so the history is scaled — basis and value together — to
    # the stated balance, and the profit fraction it carries lands a little
    # above the one typed (`lots2`).
    scale = balance / sum(lot.value for lot in lots)
    for lot in lots:
        lot.basis *= scale
        lot.value *= scale
    return lots


def gross_for_net(lots: list[Lot], method: LotMethod, net: float, rate: float) -> float:
    """Smallest sale that nets `net` after a flat `rate` on the realised gain.

    Below 60 the tax is a fixed share of the gain, so this inverse is closed
    form rather than a search: selling `t` out of a lot whose embedded gain
    fraction is `g` hands over `t * (1 - rate * g)`, so walk the lots in the
    method's own order, take each in full while it is not enough, and finish
    inside the one that covers the remainder.

    Bisecting instead — which is what the progressive-rate case above 60 still
    has to do — costs sixty passes over a pool that can hold nine hundred lots,
    every month of the horizon, for the same answer to fifteen decimals.

    A pool too small to cover `net` returns more than it holds; the caller
    clamps to the balance and books the difference as a shortfall.
    """
    if net <= 0 or not lots:
        return 0.0
    order = (
        range(len(lots)) if method is LotMethod.FIFO else range(len(lots) - 1, -1, -1)
    )
    remaining = net
    gross = 0.0
    for index in order:
        lot = lots[index]
        if lot.value <= 0:
            continue
        per_shekel = 1 - rate * lot.gain_fraction
        if per_shekel <= 0:
            return gross + lot.value
        if lot.value * per_shekel >= remaining:
            return gross + remaining / per_shekel
        gross += lot.value
        remaining -= lot.value * per_shekel
    return gross + remaining


def realised_gain(
    lots: list[Lot], method: LotMethod, gross: float, commit: bool = True
) -> float:
    """Gain realised by selling `gross`, oldest- or newest-first.

    With `commit=False` the pool is left untouched, which is what the tax
    gross-up needs while it searches.
    """
    if gross <= 0 or not lots:
        return 0.0
    order = (
        range(len(lots)) if method is LotMethod.FIFO else range(len(lots) - 1, -1, -1)
    )
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
