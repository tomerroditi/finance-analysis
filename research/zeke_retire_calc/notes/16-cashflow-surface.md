# The monthly cash-flow surface

The reference publishes two charts we had never compared against: `income_plot`
and `expense_plot`. They are worth far more than the balances, for one reason —
**they are a closed decomposition**. In all 134 recorded runs the two sides
balance to the agora, every month:

```
work + one-off income + every annuity + every withdrawal + the unfunded gap
  = living costs + one-off spending + debt + every tax + every deposit
    + the cash-buffer top-up + whatever is left in checking
```

The asset series only ever show the net effect of a month. These rows show the
month itself: which bucket funded it, in what order, what tax each individual
sale paid, how a pension split into its recognised and entitling halves, and
what each person's national-insurance base was.

## The rows

| chart row | meaning | our key |
|---|---|---|
| `עבודה` | recurring income | `work` |
| `הכנסות חד פעמיות` | one-off income — **and a severance redemption** | `one_time` |
| `משיכה מעובר ושב` | drawn from checking (including into overdraft) | `cash` |
| `משיכה מתיק X` | drawn from a portfolio, **gross of the tax** | `portfolio{i}` |
| `משיכה מקרן השתלמות X` | drawn from a study fund | `keren{i}` |
| `מוכרת` / `מזכה` | recognised / entitling pension annuity, per person | `recognised`, `entitling` |
| `מוכרת גמל להשקעה` | annuitised gemel, per person | `gemel{i}` |
| `קיצבת זיקנה` | Bituach Leumi old-age pension, per person | `state_pension` |
| `החתיכה החסרה` | "the missing piece" — what the plan could not fund | `shortfall` |
| `הוצאות שוטפות` | recurring spending | `living` |
| `יעדים` | one-off spending | `one_time` |
| `הלוואות` | debt service | `loans` |
| `מס על רווחי X` | capital-gains tax on that portfolio's sale | `capital_gains_tax{i}` |
| `מס הכנסה` / `ביטוח לאומי` | income tax / national insurance on the annuity | `income_tax`, `national_insurance` |
| `הפקדה לX` | surplus routed into a portfolio | `deposit_portfolio{i}` |
| `הפרשה לעובר ושב` | surplus routed into the cash buffer | `buffer` |
| `הוצאה לא מתוכננת` | surplus that found no destination | `unplanned` |

One-off flows are charted apart from recurring ones on **both** sides —
`הכנסות חד פעמיות` and `יעדים` — which is how a `one_time` row is told from a
`now`-to-`forever` row of the same size.

## Two bugs it caught immediately, neither visible in any balance

**A severance redemption re-split the pension the wrong way.** Redeeming the
entitling employer severance takes `balance × (1 − mukeret) × 0.4` out of the
fund. We then annuitised what was left by re-applying `mukeret_pct` to the
reduced balance. The reference does not: the recognised annuity is still
`mukeret_pct` of the balance the fund had *before* the redemption, so its share
of what remains rises to `mukeret / (1 − redeemed)`. In `pn_pizuim_2010` the
reference pays 1,819.8 recognised and 2,547.7 entitling; we paid 1,310.3 and
3,057.3. The **total is identical**, which is exactly why the pension balance
and every asset series matched — but the split decides income tax, because only
the entitling half is taxable.

**National insurance was charged on too small a base.** Contributions before
the statutory age are levied on the whole annuity a person draws, an annuitised
gemel included — not just the pension fund's. In `pf_mukeret2` that is
`contributions_on(16,069.3)` rather than `contributions_on(5,153.9)`: 1,322.9 a
month against 219.0, an error of 1,103.9 every month from 60 to 67. It had been
hiding inside the three `pf_mukeret*` fixtures' large residual; fixing it cut
those from 93k–158k to 15k–57k, and what remains there is purely the unsolved
bridge (notes/15) — with the right rate supplied they replay to 2.4–7.1 shekels.

## What it now proves

`test_cashflow_parity` asserts every row of both charts, month by month, for all
134 runs. 119 match every row inside one shekel over 533 months. The rest are
listed with a bound and a reason: three are the gemel bridge, and the others are
the reference's own display rounding deciding a split — which bucket funds the
month a plan runs dry, or which of two portfolios empties first.

It also asserts the identity itself on our side: our two dicts balance to
1e-6 every month of every run, so a row that goes missing shows up as a
mismatch instead of quietly vanishing into another.
