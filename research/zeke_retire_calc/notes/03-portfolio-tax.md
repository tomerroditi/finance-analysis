# The taxed-investment-portfolio model

> **FIFO/LIFO CONFIRMED — see notes/13.** The synthetic-lot history proposed
> below is correct, and is now implemented and verified across seven scenarios.
> (An intermediate version of this note claimed it was disproved; that claim
> was itself wrong — it used the accumulation rate where the portfolio had
> switched to decumulation.)

> **CORRECTED — see notes/11.** The "age-60 exemption" recorded below is not an
> exemption. From 60 the reference switches from the flat 25% to taxing the
> gain as ordinary income on the Israeli brackets (capped at 25%), which is
> zero for modest withdrawals but distinctly non-zero for large ones.
> `fixtures/cf_rise` retires at 60.08 and is taxed for another seven years.

Companion to `01-fundamentals.md` (time grid, real-terms convention, accumulation
formula, surplus routing) and `02-input-surface.md` (field names).
Every claim below cites a fixture under `fixtures/` and the numbers that prove it.
Probes for this note are prefixed `pf_`; four pre-existing fixtures
(`tax_profit_0/50/90`, `goal_big`, `compound_precise`, `two_same`-era baselines)
are re-analysed here rather than re-run.

Legend: **[verified]** = predicted from a formula and matched the chart series to
within the chart's 0.1 ₪ rounding. **[consistent]** = the data fit the hypothesis
but a decisive discriminating probe was not run. **[open]** = not pinned down.

Multi-row scenarios are submitted by simply POSTing `portfolioBalance2`,
`portfolio_type2`, … alongside `num_portfolio_fields=N`. The `add_line` endpoint
is **not** needed — the server just reads the POST (`pf_types_all`, 6 rows).

---

## 1. Capital-gains tax — the `flat` method (exact)

Each `withdraw` portfolio carries its own **cost basis**, initialised to

```
basis(0) = portfolioBalance * (1 - portfolioProfitFraction/100)
basis    += every deposit routed into that portfolio (deposits are pure basis)
```

On a withdrawal month the engine solves for the **gross** withdrawal `W` that
nets the required amount `N` after tax:

```
p    = (A - basis) / A          # A = balance at the START of the month, i.e. the
                                #     previous month's charted 'שווי' value
rate = 0.25 * p                 # Israeli CGT 25%, applied to the profit share only
W    = N / (1 - rate)
tax  = W - N
basis -= W * (1 - p)            # the non-profit part of the gross withdrawal
```

**Rate is 25%, on the profit share of each shekel withdrawn.** [verified]

| fixture | first withdrawal | A (start of month) | basis | p | W predicted | W observed |
|---|---|---|---|---|---|---|
| `tax_profit_0` | idx 45 | 1,432,450.0 | 1,220,000 | 0.1483123 | 5,192.53 | **5,192.50** |
| `tax_profit_50` | idx 51 | 1,497,512.2 | 750,000 | 0.4991694 | 5,712.93 | **5,712.90** |
| `tax_profit_90` | idx 57 | 1,564,147.7 | 380,000 | 0.7570562 | 6,167.24 | **6,167.20** |
| `pf_types_all` (P1) | idx 2 | 351,396.6 | 175,000 | 0.5019872 | 5,717.53 | **5,717.50** |
| `pf_kaspit_pikadon` (P1) | idx 2 | 903,591.4 | 450,000 | 0.5019873 | 5,717.53 | **5,717.50** |
| `pf_two_same` (A1) | idx 51 | 887,345.8 | 500,000 | 0.4365218 | 5,612.49 | **5,612.50** |
| `pf_two_same` (A2) | idx 235 | 885,020.7 | 250,000 | 0.7175207 | 2,717.58 | **2,717.60** |

Max residual ±0.04 ₪ = chart rounding.

Basis roll-forward, `tax_profit_0` idx 45 → 46: after W=5,192.53 at p=0.1483123
the basis becomes `1,220,000 − 5,192.53·0.8516877 = 1,215,577.59`; with
A[45]=1,430,185.0 that gives p=0.1500557 → W=5,194.88 vs **observed 5,194.90**.
[verified]

Note in `tax_profit_0` that `portfolioProfitFraction=0` still produces tax
(192.50 in the first withdrawal month): the profit fraction is a *state variable*
that grows with the portfolio, not a fixed rate. Deposits dilute it (they are
pure basis), growth inflates it, and withdrawals leave it unchanged (proportional
basis consumption), so under `flat` **p rises monotonically through decumulation**
(`tax_profit_50`: 0.4991 at 40.8 → 0.6853 at 60.0).

Each portfolio row has its **own independent basis** — `pf_two_same` A1 (which
absorbed all 50 deposits, basis 500,000) and A2 (untouched, basis 250,000) are
taxed off different fractions in the same run. [verified]

### The age-60 exemption

**From the month after the retiree's 60th birthday, portfolio withdrawals are
completely untaxed.** [verified]

`tax_profit_0`, `tax_profit_50`, `tax_profit_90` all switch at index 281→282
(age 60.0 → 60.08, DOB 1990-01-01): e.g. `tax_profit_50` W=6,033.80/T=1,033.80
at 60.0, then W=**5,000.00**/T=**0.00** from 60.08 onwards, forever. The balance
still falls by exactly the gross: `(310,591.3 − 5,000)·1.0022 = 306,263.6`
(`pf_types_all` P4, idx 281→282) — so it is a genuine exemption, not a change of
funding source.

It is keyed to **age**, not to FIRE date and not to `pension_tactics`:

- `pf_types_all` (FIRE 36.75) and `tax_profit_0` (FIRE 40.33) both cut over at
  index 282 — same DOB, same cutover. [verified]
- `pf_tactics67` is `tax_profit_50` with `pension_tactics=67`: **every chart
  series is byte-identical**, cutover still at 60.08. [verified]
- It applies to every `portfolio_type` (seen on `portfolio`, `polisa` in
  `pf_types_all`; on `kaspit` in `pf_kaspit_pikadon`).

This is a modelling choice of the calculator, not Israeli law for a plain
brokerage account. Treat it as a behaviour to replicate or deliberately reject,
not as a tax rule.

### `portfolio_fifo_lifo` — lot accounting

All three methods use the same 25% rate on the profit share; they differ only in
**which lots the withdrawal is deemed to come from**, i.e. in `p`.
Same scenario (1,000,000 @ 50% profit, 5,000/mo deposits, goal 9M):

| method | fixture | FIRE age | p at first withdrawal | p at age 60.0 |
|---|---|---|---|---|
| flat | `tax_profit_50` | 40.8 | 0.4991 | 0.6853 |
| fifo | `pf_fifo` | 41.0 | **0.7681** (falls) | 0.5901 |
| lifo | `pf_lifo` | 40.6 | **0.0040** (rises) | 0.8049 |

Direction is as expected: FIFO sells the oldest (most-appreciated) money first
and its taxable share *decreases*; LIFO sells the newest deposits first and
starts at almost zero tax, rising as it eats backwards. FIRE date moves with it
(41.0 / 40.8 / 40.6).

**LIFO's first withdrawal is exact.** [verified] The newest lot is the previous
month's 5,000 deposit, one month old, so its gain fraction is
`1 − f⁻¹ = 1 − 1/1.0039906 = 0.00397474`, rate `0.00099369`,
`W = 5000/(1−0.00099369) = 5,004.97` — **observed 5,005.00, tax 5.00**.

**The opening balance is expanded into a synthetic purchase history.** [consistent]
Under FIFO the taxable share of the very first withdrawal is far higher than the
opening lot's own gain fraction would allow (0.768 vs 0.595), and it then *falls
smoothly* — which only happens if the opening balance is many lots of different
ages, not one. Reading the implied lot age back out of `p`
(`age = −ln(1−p)/ln f`, correcting for the two growth regimes) gives the age of
the oldest surviving synthetic lot:

| fixture | profit fraction q | oldest synthetic lot at first withdrawal | M predicted |
|---|---|---|---|
| `pf_fifo_nodep` | 50% | **313.5 months before t=0** | 314.7 |
| `pf_fifo_p90` | 90% | **906.3 months before t=0** | 907.0 |

`M predicted` solves "a stream of **equal monthly deposits** over the previous
M months, compounding at `f = ((1+i)(1−fee))^(1/12)`, has exactly q unrealised
profit today":  `f(f^M − 1)/((f−1)·M) = 1/(1−q)`. The two independent q values
land within 0.4% and 0.08% of the prediction (a consistent ≈1-month shortfall
that is probably an index convention, or the history compounding at the gross
`1.05^(1/12)` instead of the net `f`). The marginal lot then advances forward
through that history at ≈1.17 synthetic months per calendar month
(`pf_fifo_nodep`: −313.0 at t=17 → −194.2 at t=119).

`p` moves in 1–6 rounding units per month with no real plateaus, so the
implementation is effectively a continuum of lots, not chunky annual lots.
The exact reconstruction rule is **[open]** — verified in shape and in scale,
not to the shekel.

---

## 2. `portfolio_type` — what actually differs

Six types were run **side by side in one scenario**, identical in every other
input (350,000 each, 5% / 0.1%, profit 50%, `withdraw`): `pf_types_all`.
A US-citizen twin: `pf_american`.

**Growth, fees and tax rate are identical across all six types.** [verified]

- Accumulation factor, all six: `A[1] = 351,396.6 = 350,000 × 1.0039906`
  — i.e. `((1+i)(1−fee))^(1/12)`, no type-specific fee or return adjustment.
- Tax on withdrawal, 25% on the profit share, verified individually on
  `portfolio` (P1, 5,717.50), `ibkr` (P2, T/W=0.142055 vs predicted 0.1420686),
  `gemel` (P3, 53.00/335.00 vs predicted 0.1582657), `polisa`
  (P4, 601.70/3,450.30 vs predicted 0.1743963), and in `pf_kaspit_pikadon`
  on `pikadon` (P1, 5,717.50) and `kaspit` (P2 idx 191: predicted 6,008.15,
  observed 6,008.30).
- No type is tax-exempt, and none has a different rate. `kaspit` looked exempt in
  `pf_types_all` only because it was not reached until age 65.6 — past the
  universal age-60 exemption. `pf_kaspit_pikadon` draws it from age 52.4 and it
  is taxed normally.
- No type has a special withdrawal tax, penalty, or exit fee.

**The two real differences:**

**(a) `gemel` has a hard annual deposit ceiling of 76,449.6 ₪ = 6,370.8 ₪/month.**
[verified] `pf_deposit_caps` gives all six types a 20,000 ₪/mo deposit cap and a
200,000 ₪/mo surplus; five types take the full 20,000 every month, `gemel` takes
**exactly 6,370.8** every month (76,449.6/yr). The ceiling is applied as a flat
monthly twelfth — it cannot be front-loaded. 76,449 ₪ is the Israeli
*kupat gemel le'hashkaa* ceiling for tax year **2023**, so the constant is stale
relative to 2026 (81,711 ₪ in 2025).

The ceiling is **per account, not per person**: `pf_gemel_two` has two `gemel`
rows and *each* gets 6,370.8/mo (152,899/yr in total). [verified] That is not how
the real ceiling works (it is per individual), so it is a modelling bug worth not
copying.

**(b) only `gemel` can be annuitised into a קצבה מוכרת** — see §3.

**`is_american` does nothing.** [verified] `pf_american` is `pf_types_all` with
`is_american=yes`: *every* chart series and the summary text are byte-identical.
`pf_american_kh` (US citizen, `gemel` portfolio + Keren Hishtalmut) is likewise
byte-identical to `pf_kh_prati`. No PFIC treatment, no extra US tax layer, no
restriction on which instruments a US citizen may hold. The only place the flag
surfaces is the free-text recommendation engine.

Type also steers the (non-numeric) recommendation strings: a `gemel` in the plan
produces "פידיון קופת גמל להשקעה", a Keren Hishtalmut produces
"העברת קרנות השתלמות ל-IRA", and `pf_american_kh` adds
"פתיחת תיק השקעות בניהול עצמי".

---

## 3. `portfolioDesignation`: `mukeret_main` / `mukeret_partner`

**A `mukeret_*` portfolio is annuitised in full at age 60 into a tax-free
"recognised annuity" (קצבה מוכרת) for the named person — but only if its
`portfolio_type` is `gemel`.** [verified]

`pf_mukeret2` (one withdraw portfolio + four idle ones: gemel/goal,
gemel/mukeret_main, polisa/goal, polisa/mukeret_main):

```
              A[281] (age 60.0)   A[282] (age 60.08)   A[533] (age 81)
G2 gemel/goal      2,449,615.5        2,459,390.5        6,682,646.0
M3 gemel/mukeret   2,449,615.5                0.0                0.0
G4 polisa/goal     2,449,615.5        2,459,390.5        6,682,646.0
M5 polisa/mukeret  2,449,615.5        2,459,390.5        6,682,646.0
```

and the annuity list gains
`M3 קופת גמל להשקעה - גמל להשקעה מוכרת קצבה מגיל 60 בגובה 10,915.5 ₪ (מקדם 224.4)`.

Annuity = balance at age 60 ÷ the same annuity factor (מקדם) the pension uses:
`2,449,615.5 / 224.4 = 10,916.29` vs observed **10,915.5** (0.007% — the printed
224.4 is itself rounded). [verified]

- **Gate is the type, not the list position.** `pf_mukeret4_order` lists the
  polisa `mukeret_main` row *first* (MP2) and the gemel ones after; MP2 still
  does not convert, MG3 (gemel) does. [verified]
- **Not gated on `pension_tactics`.** `pf_mukeret3_t60` repeats `pf_mukeret2`
  with `pension_tactics=60` instead of `60-67`; M3 still converts to the same
  10,915.5 ₪. [verified]
- **`mukeret_partner` is the same thing for retiree 2.** `pf_mukeret4_order`
  PG4 (gemel, `mukeret_partner`) converts into S's list at
  **10,775.0 ₪ (מקדם 227.3)**; `2,449,615.5/227.3 = 10,777.01`. The factor
  differs because it is the partner's (female, own statutory age). [verified]
  With no partner declared, `mukeret_partner` is inert.
- **The proceeds are untaxed.** In `pf_mukeret2` at index 282 the household
  receives 5,153.9 (pension mukeret) + 10,915.5 (gemel mukeret) and
  `מס הכנסה = 0.0`; only `ביטוח לאומי = 1,323.0` is charged. [verified]
- **Conversion is unconditional, not need-driven.** In `pf_mukeret2` the
  household only needs 5,000/mo, so 9,746.4/mo of the annuity spills into
  "הוצאה לא מתוכננת" and piles up in the checking account earning nothing.
- **Before 60 a `mukeret_*` portfolio behaves exactly like `goal`** — it is not
  available to fund living expenses. In `pf_mukeret2` W1 is drained to ~8k by
  age 60 while M3 sits untouched, and G2/M3 track each other to the shekel until
  the conversion month.
- On a **non-`gemel`** type, `mukeret_main`/`mukeret_partner` are numerically
  **indistinguishable from `goal`**: `pf_mukeret_ref` (goal), `pf_mukeret_main`
  and `pf_mukeret_partner` — all with a `portfolio`-type row — produce
  byte-identical chart series and summaries. [verified]

Every `goal` / `mukeret_*` portfolio also gets its own line in the goals
check-list (`V X2: הושג`).

---

## 4. `prati_hishtalmut_order` — which bucket is drawn first

**It selects whether the taxed portfolios or Keren Hishtalmut is drawn down
first, and nothing else.** [verified] `pf_kh_prati` / `pf_kh_hishtalmut`
(800,000 taxed portfolio + 800,000 KH, both 5% / 0.1%, income = expenses):

| | withdrawal plan |
|---|---|
| `prati` | portfolio W1 from 36.8 → 50.3, then KH 50.3 → 81.0 |
| `hishtalmut` | KH from 36.8 → 53.2, then portfolio W1 53.2 → 81.0 |

FIRE age (36.7) and net worth at FIRE (1,605,982) are identical either way in
this scenario, so the switch is pure ordering, not feasibility.

Side observation: **KH withdrawals carry no tax series at all** — the
`expense_plot` only ever contains `מס על רווחי W1`. KH is modelled tax-exempt.

---

## 5. Multiple portfolios — list order controls both directions

**Deposits fill portfolios in list order** (each up to its `portfolio_deposit`
cap and its `portfolio_goal`), and **withdrawals drain them in list order.**
[verified]

- `pf_two_same` — two identical rows (500,000 each, goal 9M). The
  `expense_plot` has only **one** deposit series, `הפקדה לA1`: every shekel of
  the 5,000/mo surplus goes to row 1. Withdrawals then run A1 40.8 → 56.2, A2
  56.2 → 81.0.
- `pf_types_all` — six rows drawn strictly P1→P2→P3→P4→P5 (36.8, 42.2, 48.3,
  55.7, 65.6); P6 is never touched.
- Order beats any type preference: `pf_kaspit_pikadon` lists `pikadon` **first**
  (the reverse of `pf_types_all`'s type order) and `pikadon` is drawn first.

The engine draws **cash before portfolios**: in `zero_return` the 1,050,000
checking balance funds the 5,000/mo while the portfolio sits at exactly 100,000.
Beware — the `משיכה מתיק X` income series is the *funding* line and can show
5,000 while the portfolio itself is untouched.

---

## Open questions

1. **The post-FIRE growth haircut.** After FIRE, portfolios designated
   `withdraw` stop compounding at `((1+i)(1−fee))^(1/12)` and switch to a lower,
   per-run constant factor. `goal` / `mukeret_*` portfolios keep the full rate
   (`pf_mukeret2`: G2/M3/G4/M5 all `A[100]/A[99] = 1.0039904`, while W1 runs at
   1.0021538). Undrawn `withdraw` portfolios are haircut too, so it is the
   designation, not the act of withdrawing (`pf_types_all` P6 never drawn:
   1.0021999; `pf_two_same` A2 before its first draw: 1.0020232).

   All with i=5% / fee=0.1% (full factor 1.0039904):

   | fixture | FIRE age | post-FIRE monthly | annualised |
   |---|---|---|---|
   | `pf_types_all` | 36.75 | 1.0022000 | 1.02672 |
   | `pf_fifo_nodep` | 38.0 | 1.0021485 | 1.02609 |
   | `pf_fifo_p90` | 39.0 | 1.0021076 | 1.02559 |
   | `tax_profit_0` | 40.33 | 1.0020512 | 1.02490 |
   | `pf_two_same` | 40.83 | 1.0020232 | 1.02456 |
   | `goal_big` | 49.92 | 1.0008431 | 1.01016 |
   | `compound_precise` (i=10, fee=3) | 47.33 | 0.9989171 | 0.98708 |

   Later FIRE → lower assumed return, which is the shape of a Trinity/percentile
   "safe return over the remaining horizon" (`retireRule`), but a
   `μ − z·σ/√N` fit is not consistent across the three i=5% points
   (implied `zσ` = 0.142 / 0.148 / 0.210). **Not explained.** It belongs to the
   `retireRule` area, but anyone reproducing the portfolio series must model it —
   it is the single largest unexplained term in decumulation.

2. **The exact synthetic-lot history for FIFO/LIFO** (§1). Length and shape
   confirmed at two profit fractions; the ≈1-month systematic offset and whether
   the pre-history compounds gross or net of fee are unresolved.

3. **Is the gemel ceiling ever indexed?** Only the flat 76,449.6 ₪/yr (2023
   figure) was observed. Whether the engine varies it by simulation year was not
   probed (`pf_deposit_caps` shows the same 6,370.8 in every one of the first
   four years).

4. **`kerenType` (maslulit / IRA) and KH growth.** Out of scope here, but noted:
   in `pf_kh_prati` the KH's first month grows by 1.0034865 on i=5% / fee=0.1%,
   *not* the 1.0039906 the portfolios use — the KH has its own growth formula.

5. **Whether `mukeret_*` ever changes the FIRE date.** In every probe run the
   conversion happened at 60 and the household was already over-covered, so the
   designation never relieved the pre-60 funding constraint. A scenario where the
   plan fails without the annuity was not constructed.

---

## Fixtures produced for this note

| fixture | what it isolates |
|---|---|
| `pf_types_all` | 6 portfolio types side by side, decumulation, draw order |
| `pf_kaspit_pikadon` | kaspit/pikadon taxed **before** 60; reversed list order |
| `pf_deposit_caps` | per-type deposit ceilings (gemel 6,370.8/mo) |
| `pf_gemel_two` | gemel ceiling is per account, not per person |
| `pf_fifo`, `pf_lifo` | lot method vs `tax_profit_50` (flat) |
| `pf_fifo_nodep` | FIFO with no deposits — clean synthetic-history read (q=50%) |
| `pf_fifo_p90` | same at q=90% — tests the history-length formula |
| `pf_tactics67` | age-60 exemption is not `pension_tactics`-driven |
| `pf_mukeret_ref/_main/_partner` | mukeret on a `portfolio` type = inert |
| `pf_mukeret2` | mukeret on `gemel` converts at 60; `polisa` does not |
| `pf_mukeret3_t60` | conversion not gated on `pension_tactics` |
| `pf_mukeret4_order` | gate is type not list order; `mukeret_partner` → retiree 2 |
| `pf_kh_prati`, `pf_kh_hishtalmut` | `prati_hishtalmut_order` |
| `pf_two_same` | deposit order and withdrawal order = list order |
| `pf_american`, `pf_american_kh` | `is_american=yes` changes nothing numeric |
