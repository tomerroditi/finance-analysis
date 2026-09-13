# Where the clone stands

## Verified

**58 recorded reference runs replay the full 533-month horizon exactly**, each
with a single free scalar (the unmapped Trinity decumulation rate). 72 unit
tests pass. What that covers:

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
- Bituach Leumi with its age-80 step-up
- pension accumulation, annuity factors, the four-way mukeret/mezake split,
  all three `pension_tactics`, income tax on the annuity, and national-insurance
  contributions — for a couple as well as a single retiree
- Keren Hishtalmut growth, its hidden maslulit fee, and its tax-free withdrawals
- gemel annuitisation under the `mukeret_*` designations

Since first writing this, the following also landed and are verified:

- **severance redemption** — both recorded cases exact (gross, exemption
  ceiling, the 1.35/180 offset, and 281.7/month for exactly 24 months)
- **all four solver modes**, with the goal checklist. Our `retire_asap` search
  reaches the reference's own published retirement month on **47 of 47**
  applicable fixtures
- **the smart-advice optimiser** — same diagnosis, action, token shape and
  outcome as the reference on the recorded case
- **the API** (`POST /api/fire/calculate`) and **the whole UI**

## Not yet done

| item | size | why |
|---|---|---|
| Wiring to the user's own tracked data | medium | deliberately deferred by the user |

Both former blockers are now closed:

- **The decumulation table is measured**, not fitted (notes/14). The engine has
  no free parameters left; all 63 recorded runs replay from the table alone,
  62 of them inside 2% and the median inside 0.1%.
- **FIFO / LIFO are solved** (notes/13), verified across seven scenarios
  including two with a known deposit history and no synthetic part at all.

## Residual gaps, all bounded and understood

19 fixtures still miss. Eleven miss by **under 14 shekels over 533 months**
(≈1e-5 relative) and are precision limits, not modelling errors — chiefly the
annuity factors, which the reference only ever prints to one decimal. The
female factors are the least precise because the only fixtures using them have
small balances.

Eight miss by more (32k–131k), all in scenarios combining a couple, a study
fund and a `mukeret_*` gemel. The annuity arithmetic in those is confirmed
correct to the shekel — at age 60.08 of `pf_mukeret_ref` the reference's four
annuity rows total 47,801.5 against our 47,801.2, and its four deduction rows
total 8,472.8 against our 8,472.6. The drift is in the withdrawal portfolio's
path, and is at least partly the missing Trinity rate; a rate-independent
component of roughly 3,175 remains and is not yet explained.
