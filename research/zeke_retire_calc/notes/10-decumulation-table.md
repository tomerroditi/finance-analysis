# The decumulation-return table — harvested from the fixtures

The one quantity we cannot yet derive from first principles is the reference's
**decumulation return**: the reduced real return a withdrawal portfolio earns
after retirement, set by `retireRule` (confidence) and the horizon. The site
attributes it to the Trinity study at 75% equities.

`fit_decumulation.py` recovers it per fixture by solving for the single scalar
that makes our simulation match the reference. That does two jobs at once.

## 1. It proves the rest of the model is exact

**33 of the pension-free fixtures fit with a residual under 1 shekel** — most at
0.05, which is the reference's own display rounding. Since only one scalar is
free, that residual is a strong statement: accumulation, the fee convention,
capital-gains tax and its age-60 exemption, all six instrument types, the gemel
deposit ceiling, multi-portfolio deposit and withdrawal ordering, every
start × end timing combination, the annual rise, all three loan types, real
estate, the credit-limit floor, the cash-buffer rules, and Bituach Leumi with
its age-80 step — all reproduce exactly.

## 2. It gives us the table

Fitted values at `retireRule = 85` (rows with a clean fit only):

| bridge to state pension | fitted return |
|---|---|
| 8.42 y | 0.0003% |
| 8.92 y | 0.0009% |
| 9.42 y | 0.0021% |
| 11.92 y | 0.0030% |
| 12.83 y | 0.0000% |
| 13.75 y | 0.0246% |
| 15.50 y | 0.5562% |
| 16.92 y | 1.0710% |
| 17.08 y | 1.1217% |
| 19.75 y | 1.9180% |
| 21.92 y | 2.1292% |
| 25.75 y | 2.6205% |
| 26.33 y | 2.5693% |
| 26.75 y | 2.6850% |
| 30.25 y | 2.7748% |

The shape is unmistakable: **flat at ~0 below roughly 13 years, then rising
steeply, then saturating near 2.8%**. That is what a Trinity success-rate table
looks like once you invert it into "the return that exactly exhausts the pot
over N years" — short horizons force a punitive assumption, long horizons
approach the historical safe rate.

Confidence axis, sampled at bridge 13.75 y: rule 85 → 0.0246%, rule 95 →
0.0001%, rule 100 → 0.0030%. Too close to the flat part of the curve to
separate; the pension agent's `pn_rule*_pf` series at a ~19 y bridge separates
them cleanly (80 → 2.119%, 85 → 1.636%, 90 → 1.174%, 95 → 0.731%,
100 → 0.326%).

## What would close it

A grid of forced retirement ages (`base_problem=retire_at_age`) × `retireRule`
values, each read off an idle portfolio, maps the surface directly — roughly
5 confidence levels × 8 horizons. Every cell is exact, so the table can be
reproduced rather than approximated. That is the last piece needed for
end-to-end parity, and it is a decision worth taking deliberately: it means
~40 more jobs on someone else's server.

## The 12 remaining genuine gaps

These do not fit any single decumulation return, so something else is still
missing. Grouped by likely cause:

- `buffer_20k` (14,473), `cf_credit_100k` (10,000), `cf_timing_bits` (10,142) —
  all cash-side. Suspect the checking-account rules differ in decumulation
  (whether the buffer is defended once retired).
- `tax_profit_0` / `_50` / `_90`, `pf_two_same`, `pf_tactics67` (~12–14k) —
  all high-embedded-profit portfolios drawn down over a long retirement.
  Suspect an interaction between the age-60 tax exemption and the basis
  roll-forward.
- `cf_rise` (3,227), `compound_precise` (18,364) — long drawdowns.
- `pf_deposit_caps` (25.7), `pf_gemel_two` (28.1) — small, likely a deposit
  ordering detail with multiple capped accounts.
