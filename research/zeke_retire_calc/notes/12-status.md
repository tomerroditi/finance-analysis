# Where the clone stands

Measured by `python research/zeke_retire_calc/parity.py` over every recorded
reference run (all three charts plus net worth, every month, relative to the
run's peak net worth), and asserted run by run by `test_corpus_parity.py`.

## The headline

| | runs | under 0.1% |
|---|---|---|
| everything recorded | 1,694 | 1,649 |
| single-person plans | 1,640 | 1,638 |
| couples | 54 | 11 |
| random multi-feature households (`cx1_*`) | 39 | 25 |

Every single-person run is under 0.1% bar two, and both are the FIFO/LIFO
lot approximation (0.22% and 0.43%). Everything else over the target is a
couple. The random households are the acceptance test: 40 plans drawn from a
seeded generator using every feature at once — couples, several portfolios of
mixed types and designations, study funds, loans started in the past, real
estate, one-off flows, rising costs, every pension tactic, severance.

## What changed in the model (notes/18)

- **The surface is measured, not fitted.** Every whole-year bridge 7–45 for
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
- **A couple runs until the younger spouse is 81**, and **its capital gains are
  taxed on the older spouse's age**.
- **One-off rows count toward the coverage by their end type** (`forever` by
  default), so a windfall before 60 can cancel the spending entirely.
- Surtax above 721,560/yr; the national-insurance ceiling at 51,910/month;
  `retire_at_age` retiring a month early; float dust stretching a drawdown
  segment.

## Open

| item | size | notes |
|---|---|---|
| **A couple's bridge** | up to ~18% on couples | Pension-free couples read a fixed-weight blend of the two statutory waits (0.5203 on the later, gaps ≤ 5 years, both genders, either spouse older); a partner's own pension reads exactly as a single person's; the man's pension beside a woman partner fits neither. `experiments/couple*.py`, notes/18 §6. |
| FIFO/LIFO lot history | ≤ 0.43% | The reference's synthetic purchase history is compressed at both ends relative to ours (notes/13). |
| Confidence off the grid | ~0.03% at 85.5 | Rules other than 80/85/90/95/100 interpolate; rule 87 at 15 years is 0.120 against 0.196 linear. |
| Drawdown prose on random households | presentation only | Segments break differently from ours where every monthly series agrees; the result-section tests cover the curated fixtures only. |
| Wiring to the user's tracked data | medium | deferred by the user |
