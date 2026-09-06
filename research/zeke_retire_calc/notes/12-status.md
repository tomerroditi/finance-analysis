# Where the clone stands

## Verified

**Every one of the 134 recorded reference runs replays the full 533-month
horizon with nothing fed in** — the engine derives its own decumulation return.
**115 of them land inside a tenth of a shekel** on every series in every one of
those months, which is the reference's own display step; 126 land inside 15
shekels, and the eight that do not are the named gaps below.

Four changes took the corpus from a summed worst-case of 517 shekels to 206,
each worth a few shekels a month and tens over the horizon once compounded:

* the surface's cells were being stored rounded to four decimals — four
  decimals of an annual rate moves the monthly growth factor by 4e-9, which is
  invisible in a month and worth tens of shekels over 533 of them;
* the annuity factors were each read off a single fixture, where the
  reference's one-decimal print leaves a thousandth of slack. They are now
  bracketed across the whole corpus and placed inside those brackets by replay
  error, which is a thousand times finer. The 14 runs annuitising at male 67
  replay to a combined **0.95 shekels**, and `pf_mukeret_ref` and its two
  siblings went from 51 shekels to 2.5;
* the synthetic lot ladder was one lot too long — summing it from `a = 1`
  rather than `a = 0` halves the tax disagreement on every fixture that has a
  manufactured purchase history (notes/13);
* and one about evidence rather than arithmetic: a cell voted on by both a
  clean run and one carrying a fifty-shekel lot-history residual was being
  averaged, handing the clean run a rate it could not replay. The clean vote
  now wins outright, which took `tri_r85_a38` and `pn_bl_income_work` off the
  gap list entirely.

Three suites assert it. `test_reference_parity` replays all 134 balance series
with no input, and separately replays the 125 runs that pin their own rate to a
two-shekel tolerance with that rate supplied — the tighter statement about
everything other than the surface. `test_cashflow_parity` asserts the
reference's other two charts, `income_plot` and `expense_plot`, row by row and
month by month: a *closed* decomposition of every shekel in and out, which is
what pins the withdrawal order, the deposit routing, the tax on each individual
sale and each person's national-insurance base — 126 of the 134 match every row
inside 0.15 shekels (notes/16). `test_result_sections_parity` covers the rest of
the result page against the reference's own prose and doughnuts: the goal
checklist, the annuity list, the drawdown plan, both asset cards, and the
closing pension line. And
`test_feature_combinations` runs plans nobody recorded — every instrument at
once — against identities rather than fixtures.

What that covers:

- the monthly grid, the fixed age-81 horizon, month-granular dates
- portfolio growth with the multiplicative fee convention
- the two-phase switch at retirement, and which accounts it applies to
  (withdrawal portfolios and study funds, but not goal portfolios)
- capital-gains tax: flat 25% below 60, marginal-rate treatment above,
  the statutory-age exemption, and basis roll-forward
- all six instrument types, the gemel deposit ceiling (76,449/yr, per account)
- multi-portfolio deposit and withdrawal ordering, deposit caps, goal ceilings
- every start × end timing combination, one-time flows, the annual rise
  anchored per row
- spitzer / balloon / grace loans and their effect on net worth
- real estate, the credit-limit floor, cash-buffer rules
- Bituach Leumi: the flat amount, the age-80 step-up, and the spouse increment
  paid while one partner is eligible and the other is not (notes/15)
- the four annuity factors, each bracketed by the corpus and placed inside its
  bracket by replay error (`measure_annuity_factors.py`, `tune_annuity_factors.py`)
- pension accumulation, annuity factors, the four-way mukeret/mezake split,
  all three `pension_tactics`, income tax on the annuity, and national-insurance
  contributions — for a couple as well as a single retiree
- Keren Hishtalmut growth, its hidden maslulit fee, and its tax-free withdrawals
- gemel annuitisation under the `mukeret_*` designations
- severance redemption — both recorded cases exact
- FIFO / LIFO lots, including the manufactured purchase history (notes/13)
- all four solver modes; `retire_asap` reaches the reference's own published
  retirement month on 47 of 47 applicable fixtures
- the smart-advice optimiser
- every section of the result page, each against the reference's own output:
  the verdict, the goal checklist, the annuity list (one row per component,
  with claim ages and annuity factors), the drawdown plan, both asset cards
  with their shortfall slice, and the closing pension line (notes/16)
- the API (`POST /api/fire/calculate`) and the whole UI

## The decumulation surface has no free parameters

The engine reads it on the **bridge** to the pension, gender-aware and weighted
by the annuities the plan actually starts (notes/15). Every cell is measured
off a recorded run that pins it to within 0.0005 points
(`build_decumulation_table.py` re-derives the whole table and re-checks that
pinning on each build). Where two runs vote on the same cell and one of them
replays an order of magnitude better, only the better one is counted.

## Not yet done

| item | size | why |
|---|---|---|
| Wiring to the user's own tracked data | medium | deliberately deferred by the user |

## The one open question

Three fixtures — `pf_mukeret2`, `pf_mukeret3_t60`, `pf_mukeret4_order` — miss by
15k–57k. All three hold a **gemel portfolio earmarked `mukeret_*`**, and the
bridge such a conversion implies does not follow the rule the other 131 obey.
Fully characterised, with seven disproved alternatives, in notes/15. Given the
right rate all three replay to 1.5-2.8 shekels, so what is unexplained is one
scalar each. It needs fresh probes of the live reference to settle; the bounds
are asserted meanwhile so it cannot silently drift.

## Also covered, since the cash-flow surface landed

- every input field the reference's form has is parsed, and a value that cannot
  be is a 400 naming the field rather than a 500
- `אין תוצאות להצגה` — a person past the search window or past the horizon gets
  no plan at all, as in `old_66`
- the API itself (`tests/backend/routes/test_fire_routes.py`), including that a
  scenario using every instrument comes back with every row intact
- degenerate inputs the recorded runs never cover: a portfolio that does not
  grow, a balance declared 100% profit, a fee that takes everything, no income,
  no spending, a loan starting past the horizon

## The residuals

Everything outside 15 shekels is a named, bounded approximation. The synthetic
lot history (notes/13) is the largest: it costs 468 shekels on `lot_lifo_nodep`
and 276 on `pf_lifo` — 0.03% and 0.02% of those portfolios — and 35-39 on the
two FIFO runs. Interpolating the surface for a split pension claim costs 260 on
`pn_annuity_6067`.

The lot figure grew rather than shrank, and deliberately: those runs used to
set their own surface cells, so the table absorbed their error and handed it to
the clean fixtures sharing those cells. Now their votes are dropped in favour
of the clean ones, and the approximation shows its own cost instead of
spreading it.

`pn_annuity_6067` is the last of them, and it is the surface's own
interpolation rather than a modelling gap. It is the only run that genuinely
reads two bridges, and its shorter one lands in the collapsed stretch where the
surface is 0.0002 — so the blend reduces to the longer stream's weight times
`S(18)`, and solving it gives `S(18) = 1.3462` against the 1.3559 the table
interpolates. Rule 85 is measured at 17.25 and 18.333 and nowhere between, over
a gap where the curve climbs 26%. A single probe of the reference at a bridge of
18.0 would close it (notes/15).
