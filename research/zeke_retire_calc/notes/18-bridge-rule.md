# The bridge rule, measured — and the surface under it

Supersedes notes/15 §3 ("weighted by what it pays") and the post-60 shift of
notes/14/15. Everything here comes from live probes recorded 2026-09 with
`lab.py`; the fixture families are named in each section.

## 1. The surface is now measured, not fitted

`experiments/surface.py` parks 1e9 in an idle withdrawal portfolio with no fee
and a 20% return (so `min(table, return)` never binds), gives the plan 20M of
cash so the portfolio is never touched, and pins the retirement age. The
post-retirement growth of that portfolio *is* the surface value, and at 1e9
printed to one decimal it is pinned to ~1e-9 — the first probe read 2.1291674
against the 2.1291674 the old table held for bridge 22.

* `wanted_retire_age` must be a whole number (the reference answers 45.5 with
  `כשל בביצוע`), and the last working month is the one at exactly that age, so a
  pinned plan only ever reads whole-year bridges. 195 cells: rules 80/85/90/95/100
  × bridges 7–45 years.
* The confidence field takes any whole number from 80 — rule 82 and 87 answered
  (`sf_r82_*`, `sf_r87_*`). Confidence does **not** interpolate linearly: rule 87
  at bridge 15 reads 0.1201 against 0.1961 on a straight line from 85 to 90.
  Linear in the withdrawal rate is no better.
* The surface is **not monotone**: rule 80 peaks at 3.1907 at a 40-year bridge
  and falls to 3.1745 by 45. The implied withdrawal rate has irregular third and
  fourth differences at particular horizons. It is an empirical surface, not a
  formula — which is why it ships measured.
* Below ~14 years every level sits at `1/N` (a real return floored at zero), with
  noise of up to 0.005 points that looks like a bounded optimiser's leftovers.
* Fractional bridges are **not** a linear interpolation of the whole-year cells in
  any space tried — rate, withdrawal rate (immediate / due / monthly), annuity
  factor, cumulative growth, log growth, or a Box-Cox family between those two
  (p = 0.75 is within 1e-5 past 18 years but 0.005 off in the knee). So
  fractional cells are measured too (`surface_fine`, §4).

What the old table got wrong: four cells at 26.45, 27.45, 28.45, 29.45 were
post-60 runs placed on the pre-60 curve through the assumed `+23.45` shift. They
sat a fortieth of a year from genuine cells with the same rate, and distorted
PCHIP around them enough to make `be_age40_s10` look age-dependent.

### Update: it is a formula after all

The author's post "אלגוריתם למשיכות משתנות מתיק השקעות תוך שמירה על הסיכון
הממוצע" gives it: `SWR% = 379 / (confidence^0.6 * years^0.5)` (an empirical fit
to the updated Trinity tables, 75% equities), converted to a real return with
the annual annuity-due identity and floored at zero. The constant is backed out
of the post's three worked examples (85%/40y 2.95, 85%/27y 2.608, 90%/22y 1.77:
378.99, 379.01, 379.01). It reproduces the measured cells past ~22 years to
~1e-5 — median 5e-6 on rule 85. What the measurements add is the reference's
solver drift: always upward, a one-year sawtooth up to 0.05 points in the knee.
No Newton-Raphson variant tried (start, tolerance, stopping rule, numeric
derivative) reproduces it, so the engine ships formula + measured drift, and
interpolates the drift — not the rate — for confidences between the measured
five. Held out, rules 82 and 87 come back within 0.007 points in the knee and
0.001 elsewhere.

### Update 2: the drift is the author's solver, and it is exact

The drift is not noise to measure but the reference's Newton-Raphson stopping
early, and it is now reproduced step for step (`decumulation.py`). The
iteration runs on

    f(r) = (r / w) (1 + r)^(y - 1) - ((1 + r)^y - 1)        w = 379 / (c^0.6 y^0.5) / 100

— the annuity-due identity multiplied through, so it also has a root at r = 0
— from r = 5%, and returns the first iterate with |f| < 1e-4, floored at zero.

How it was found: below the knee the reference reports small positive rates
where the exact root is negative, growing as `w y -> 1` and resetting, which is
an iteration creeping toward a root at zero. Solving for the Newton start that
makes each cell's k-th iterate hit it exactly gave 0.0478–0.0493 for every cell
of rule 85 in `F2 = r(1+r)^y - w(1+r)((1+r)^y - 1)`, with the iteration count in
clean blocks (5, 6, 7, 6, 5) whose edges are exactly the drift's resets and
jumps; dividing by (1+r) (the form above) makes the start exactly 5% for all
1,327 cells of the five dense levels. The stopping rule is the one metric that
separates stopped from continued iterates: |f| <= 9.9687e-5 at every stop,
>= 1.0015e-4 at every step taken.

Checked on levels it never saw (`surface_offgrid`): 82 and 87 monthly through
the knee (240 cells, to 1e-10), 81, 93, 99 and the fractional 82.5 (45 cells,
to 8e-11). The confidence field accepts fractions, so a formula was the only
way to cover it. The measured cells now live in
`research/zeke_retire_calc/surface_cells.json` as test evidence; the engine
ships no table.

## 2. Coverage, not pay weights (`bridge_weights`, `bridge_end`)

Pinned at 45 with a frozen pension (no growth, deposits or fees, so the annuity
is exactly balance / factor) and the rate fitted per run:

* **A gemel converted at 60 changes nothing.** `gb2_t{60,6067,67}_{400,1600}k` read
  exactly the rates of the gemel-free runs (0.32106 / 1.93563 / 2.12917).
* **Spending matters.** At the same 60/67 split the rate runs from 1.258 (2k of
  spending) to 2.090 (20k).
* Runs with the same **x = (pension started at 60) / (spending)** read the same
  rate to five decimals — `bw_exp_20k` (1,604/20,000) and `bw_bal_300k`
  (401/5,000) both 2.08987/6; `bw_t60_bal300k` and `bw_t60_exp20k` (tactic 60)
  both 1.97572.
* That rules out any schedule simulation: `be_exp_end60` (5,000 until 60, 3,000
  after) and `bw_share_50` have different spending paths and the same x, and
  read 1.72524 both.

What counts:

| probe | change | reads as |
|---|---|---|
| `be_exp_end60` | a 2,000 row ending at 60 | excluded |
| `be_exp_from60` | a 2,000 row starting at 60 | included |
| `be_exp_rise` | the 5,000 rising 1%/yr | rise ignored (identical rate) |
| `be_inc_rent` / `be_inc_fire` | a 1,000 income from now / from FIRE, forever | **subtracted from spending** (x = 1,604/4,000) |
| salary ending at FIRE, retiring at 63 | — | not subtracted |
| Bituach Leumi, the pension's 67 share | — | not in x at all |

## 3. The blend is in the horizon, and window-scaled

Inverting each fitted rate through the surface gives the horizon it was read
at. The bridge ends inside the window between 60 and the statutory age, at

    end = 60 + (statutory - 60) · (1 - y(x))

* **Age-independent**: at x = 0.7486 the end is 63.090 / 63.089 / 63.077 for
  retirement at 40 / 45 / 50; at x = 0.1069, 66.623 / 66.624 / 66.614.
* **Window-scaled**: a woman (window 60–65) at x = 0.3167 and 0.739 lands on the
  same y as a man's seven-year window (0.1788 vs 0.178; 0.5474 vs 0.548).
* Blending in rate space, 1/N, the withdrawal rate, 1/W or log N all give weights
  that drift with the age; only the horizon holds still.

`y(x)` is measured (`bridge.COVERAGE_CURVE`, 14 points) — it starts at ≈ x/2
(0.0104 at 0.021), is 0.3441 at 0.535, 0.8546 at 0.962 and 0.9070 at 0.9946,
then jumps to 1 at full coverage (a pension that pays everything ends the bridge
at 60). None of √, x/(2−x), exponentials, logs or power laws fit it.

## 4. Past 60 the reference adds a month index to a duration (`post60*`)

With the default tactic (`60`) and no pension, a man born January 1990 retiring
at A in 61–67 reads `67 + 23.4167 - A`; a woman `65 + 23.4167 - A`; past the
statutory age both freeze (30.4167 / 28.4167). Every rule, exact to the month.

The 23 years 5 months is not a constant: born June 1985 it is 18.83, born
November 1975 the rate collapses. It is **the months from today to the month
after the 60th birthday**. In months counted from today, with `L` the last
working month and `b(c) = c - L` for a claim still ahead but `c + 1` for one
already behind:

    tactic 67:           N = b(statutory)
    tactics 60 / 60-67:  N = b(60) + W · (1 - y(x))
        W = statutory - 60            retiring before 60 or after statutory
        W = statutory - L             retiring between them

Checked by `post60_tactic` (3 ages × 3 tactics × empty / 600k pension): every
one of the 18 reproduces, including x = 0.535 → y = 0.344 and x = 0.160 →
y = 0.083 read off the pre-60 curve. `b(c) = c + 1` for a claim behind the
retirement is almost certainly a bug on the reference's side (an index from
today used as a wait); it is cloned because it is what users see.

This also makes a measuring instrument: a man retiring at 61 reads
`6 years + months-to-60 + 1`, so moving his birth month moves the bridge one
month. `surface_fine` uses it to measure the surface at monthly resolution.

## 5. Other things found on the way

* **Surtax** (`fx_m67_20m`, `fx_f67_20m`): the annuity's income tax has a 50% row
  above 721,560 a year — 135.9 and 15.5 a month, exactly 3% of the excess.
* **National-insurance ceiling** (`fx_m60_20m`): contributions stop at 51,910 a
  month (89,119.7 drawn, 5,588.0 paid).
* **After 60, capital gains stack on the taxed person's entitling annuity** in
  the income-tax brackets (the author's gemel post: a taxable pension makes the
  same gain cost more). It was the whole of `cx1_022`/`cx1_028`'s residual, not
  the lot history (0.22% and 0.43% → 0.005% and 0.003%).
* **`retire_at_age` retired a month early**: the last working month is the one at
  exactly the requested age; we had it one month before.

## 6. Couples: phases weighed by a running mean (`couple*.py`)

**The single-person curve is a closed form.** `y = x / (2 − x)` on the *net*
coverage fits all 14 measured points to 2e-4 (their own noise), so the window
shrinks to `(E − P)/(E − P/2)` of itself: the uncovered need after 60 over the
mean of the two need levels. A couple is the same thing over more phases.

**The rule** (every `cp*` probe to 0.01 months; every random household under
0.1%):

* Cut the time from the last working month to the **older** spouse's 81st
  birthday (the simulation itself runs to the younger's) at each spouse's
  statutory age, and at their 60th birthday unless they are on tactic `67`.
* A phase's need is the spending less the income running in its **last**
  month, floored at zero: the pension claimed at 60 (net of income tax, and of
  national insurance only until its owner's statutory age — `cp11_*_e12` read
  it 45.5 higher from 67), and from the statutory age the rest of the pension
  (gross) and the allowance (2,757; 2,911.5 past 80) — plus the 1,386 spouse
  increment while the *other* spouse is under 60 (`cp6_g108_e3k`; the
  simulation pays it until the other's statutory age).
* A phase needing the whole spending counts in full. Any other counts
  `length × need / mean`, where the mean runs over the needs of every phase
  **up to and including this one** — not over all of them. That one change is
  what the age-gap sweep (`cp5_older_087…132`: 0.23684 of a month per month
  before the younger's 60, then 0.68488), `cp_main_only` (54.66 months) and the
  younger-wife pair (70.02) all needed.
* An event already behind the retirement adds a phase of `month + 1` (the
  single-person bug, §4) at the need just before it (`cp6_*_e20k`: 452.43 and
  344.87 against 452.4 and 344.88 predicted).
* The spending is read **once, at the horizon** (`couple9`, `couple10`): a row
  that has ended by then is ignored however late it ends, one that has started
  counts from the first phase, a one-off counts as a monthly row to its end
  type, and annual rises and loans are ignored. One-off income can therefore
  drive the spending below zero, and then every phase "needs the whole of it"
  and the bridge is the whole horizon (`cx1_036`: 408 = 436 − 28).
* A severance redemption shrinks the entitling side before the claims are
  valued (`cp11`, `cx1_005`); claims are valued on the balance at retirement.

**Capital-gains tax for couples**, found on the way (`cp6_*_e20k`, `cx1_026`):
the gains are taxed on the older spouse only while the main person is under 60;
from then on on the main person (age and statutory exemption). After 60 they
stack on the taxed spouse's entitling annuity plus the other spouse's, the
latter net of the 6,110 exemption once *they* are past their statutory age.

**Found by the second random draw (`combos2`, never used for fitting):**

* **A spouse already past the statutory age today draws no allowance** — the
  same crossing rule as a pension (`cx2_042`: a wife who turned 65 in 2020 is
  paid nothing), and the bridge leaves it out too.
* **A 60th birthday in the retirement month** adds a zero-length phase at the
  full spending to the running mean (`cx2_010`: 132.4 months, the reference's
  rate to 1e-5; without it 147.4) — the single-person rule's `b(c60) = 0` case.
* **Goal portfolios must reach their targets while still working**: the
  solver retires the month after the last one first does (`cx2_018`, `037`,
  `058`), and a plan whose goal arrives only after the search window cannot
  retire (`cx2_055`).

**Also from the second draw, outside the bridge** (`tax2`, `lots2`):

* The statutory-age exemption on gains is shrunk for good by severance taken
  tax-free (`cx2_035`: by the 1,223.1 the reference prints), and while the
  other spouse's taxable annuity is stacked under the gain it covers the taxed
  spouse's own entitling annuity and nothing more (`cx2_010` fits at 1,815.8
  against 1,816; `tx2_couple_mainnone`, with none, gets none). With nothing
  stacked, the leftover still shields the gain (`tx2_single`, `cx2_035`).
* A claim falling while deposits still run is made before that month's
  deposit, after any severance redemption (`cx2_030`).
* Under tactic 60-67, a recognised share whose claim at 60 fell before the plan
  began is never claimed: the statutory claim converts only the entitling share
  and the rest stays in the fund as an asset (`cx2_016`).
* A pinned retirement age already behind today retires in the past (month
  -36 for `cx2_016`) and never switches to the decumulation return — the
  switch is an event in a retirement month the run never reaches. It is not a
  "no results" case: that is only for a search with no candidate month.
* The shortfall slice is discounted at a flat 5%, not the first portfolio's
  return (28 slices, portfolios at 3-7%, all back out to 5.000%).

Open: none on the couple bridge. The earlier readings of this section ("a fixed 0.5203
weight", "the partner's single bridge", "the plain mean of the non-zero
needs") were each one face of this rule.
