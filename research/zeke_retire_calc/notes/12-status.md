# Where the clone stands

Measured by `python research/zeke_retire_calc/parity.py` over every recorded
reference run (all three charts plus net worth, every month, relative to the
run's peak net worth), and asserted run by run by `test_corpus_parity.py`.

## The headline

| | runs | under 0.1% |
|---|---|---|
| everything recorded | 2,059 | 2,059 |
| single-person plans (incl. surface probes) | 1,932 | 1,932 |
| couples | 127 | 127 |
| random multi-feature households (`cx1_*`) | 39 | 39 |

Every recorded run is under 0.1%. The random households are the acceptance test: 40 plans drawn from a
seeded generator using every feature at once — couples, several portfolios of
mixed types and designations, study funds, loans started in the past, real
estate, one-off flows, rising costs, every pension tactic, severance.

## What changed in the model (notes/18)

- **The surface is the author's formula solved the reference's way** —
  `SWR% = 379/(c^0.6·y^0.5)` as an annuity-due real return (from his blog), by
  a Newton-Raphson from 5% that stops at |f| < 1e-4; the early stop is the
  knee's "drift" (notes/18 §1, update 2). Before the formula was found it was measured outright: Every whole-year bridge 7–45 for
  rules 80/85/90/95/100, and every month between 7 and 23 years (all of it for
  rule 85), read straight off an idle 1e9 portfolio. It is not monotone and not
  interpolable between whole years below ~22 years.
- **The bridge is not pay-weighted.** It ends at `60 + window·(1 − y(x))`,
  `x` = the pension claimed at 60 — valued at retirement, net of the national
  insurance and income tax it pays — over the spending still running after 60,
  net of other income. A gemel converted at 60, Bituach Leumi and everything
  claimed later do not count. `y` is measured.
- **Past 60 the reference adds a month index to the wait** (cloned).
- **A pension is only claimed in the month its age is crossed** — a person
  already past the claim age never draws it (cloned; `cx1_020`).
- **A goal portfolio short of its goal is filled from free cash**, not only
  from the month's surplus (`cx1_009`).
- **A couple runs until the younger spouse is 81**, but its **bridge** ends at
  the older's 81 and weighs each phase by the running mean of the needs so far
  (notes/18 §6); its capital gains are taxed on the older spouse only while the
  main person is under 60.
- **One-off rows count toward the coverage by their end type** (`forever` by
  default), so a windfall before 60 can cancel the spending entirely.
- Surtax above 721,560/yr; the national-insurance ceiling at 51,910/month;
  `retire_at_age` retiring a month early; float dust stretching a drawdown
  segment.

## Open

| item | size | notes |
|---|---|---|
| FIFO/LIFO lot history | ≤ 0.05% | The reference's synthetic purchase history is compressed at both ends relative to ours (notes/13); within target. |
| Drawdown prose on random households | presentation only | Segments break differently from ours where every monthly series agrees; the result-section tests cover the curated fixtures only. |
| Wiring to the user's tracked data | medium | deferred by the user |
