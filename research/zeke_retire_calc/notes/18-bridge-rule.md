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
* **`retire_at_age` retired a month early**: the last working month is the one at
  exactly the requested age; we had it one month before.

## 6. Couples — measured, not yet solved (`couple*.py`)

Every couple run replays to under 0.6 shekels once its own decumulation rate
is supplied, so a couple differs from a single person **only in the bridge**.
What is established:

* **The horizon runs to the younger spouse's 81**, and capital gains are taxed
  on the **older** spouse's age (both fixed in the engine).
* **Gender enters only through the statutory month.** A male partner born
  1983 and a female one born 1985 reach their statutory age in the same month,
  retire in the same month, and read the same rate to five decimals; so do
  1978/1980; and the roles are symmetric (`cp3_mainfemale_1990` =
  `cp2_empty_1990`). Pairs sharing a statutory month but not a retirement month
  (a woman born 1990 retiring in month 8, a man born 1988 in month 7) do
  differ — 353.19 against 352.49 — so the retirement month is in the rule.
* **Pension-free, the bridge end is piecewise linear in the gap `g`** between
  the two statutory months (two men, `couple4`/`couple5`, main at 364):

  | gap (months) | end | reading |
  |---|---|---|
  | 1 … 81 | `364 − 0.4797·g` | weight 0.5203 on the later statutory month |
  | 84 | 326.17 | on neither line — the partner's 67 is the main's 60 |
  | 87 … 132 | `401.6 − 0.7631·g` | a second line, jumping up at 87 |

  Rate-space and withdrawal-rate-space weights drift in both regimes; only the
  horizon is linear. The break sits where the older spouse's statutory month
  crosses the younger's 60th birthday.
* **A partner's own pension reads exactly like a single person's**, on the
  partner's window, whether the partner is the same age, older or male
  (`cp_partner_only`, `_older`, `_male`, `_t60`); the other spouse's empty
  pension contributes nothing. Two pensions add, on the woman's shorter window
  (`cp_both`).
* **The man's pension beside a pension-free woman fits neither window**
  (`cp_main_only`, `cp2_main_s*`): ends 347.9 / 334.7 / 319.4 / 288.7 at
  x = 0.10 / 0.31 / 0.51 / 0.92, against her window's 336.8 / 329.1 / 319.4 /
  288.7 — equal from x ≈ 0.5, above it below that.

Rules tried and rejected: plain averages of the two waits in horizon, rate,
withdrawal-rate, 1/N, log-N or capital (annuity-factor) space; per-person ends
averaged with household coverage; the earlier / later / partner's end alone;
the partner retiring at the main person's age; Bituach Leumi as coverage. The
reference's code is not public and its guide covers single persons only. Next:
sweep the gap for a woman beside a man, pension-free, as `couple5` did for two
men — the two slopes and the jump are the cleanest handle there is.
