# Where the clone stands

## Verified

**Every one of the 134 recorded reference runs replays the full 533-month
horizon with nothing fed in** — the engine derives its own decumulation return.
121 of them land within 30 shekels over 533 months (three parts per million of
a seven-figure balance, which is what the reference's one-decimal display
rounding compounds to), and 37 are exact to the agora.

`test_reference_parity` asserts this two ways: `TestDerivedParity` replays all
134 with no input, and `TestFullHorizonParity` replays the 119 that pin their
own rate to a two-shekel tolerance with that rate supplied — the tighter
statement about everything other than the surface.

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
- the API (`POST /api/fire/calculate`) and the whole UI

## The decumulation surface has no free parameters

The engine reads it on the **bridge** to the pension, gender-aware and weighted
by the annuities the plan actually starts (notes/15). Every cell is measured
off a recorded run that pins it to within 0.0005 points
(`build_decumulation_table.py` re-derives the whole table and re-checks that
pinning on each build).

## Not yet done

| item | size | why |
|---|---|---|
| Wiring to the user's own tracked data | medium | deliberately deferred by the user |

## The one open question

Three fixtures — `pf_mukeret2`, `pf_mukeret3_t60`, `pf_mukeret4_order` — miss by
93k–158k. All three hold a **gemel portfolio earmarked `mukeret_*`**, and the
bridge such a conversion implies does not follow the rule the other 131 obey.
Fully characterised, with the disproved alternatives, in notes/15. It needs
fresh probes of the live reference to settle; the bounds are asserted meanwhile
so it cannot silently drift.

Everything else outside 30 shekels is a named, bounded approximation: the
synthetic lot history (notes/13) costs up to 200 shekels on the five
`pf_fifo`/`pf_lifo` fixtures, a split pension claim costs 259 on
`pn_annuity_6067`, and the deposit order across two capped accounts costs 90 on
`pf_gemel_two` and `pf_deposit_caps`.
