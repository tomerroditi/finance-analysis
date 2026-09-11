# Reference calculator — established mechanics

Source: `https://zekestories.com/calculators/retire_calc/` (Django + RQ/Celery worker).
All math is server-side; the page only renders. Probing is done with `zeke.py` /
`probe.py`, which submit the real form and parse the **monthly Chart.js series**
embedded in the result HTML (`income_plot`, `expense_plot`, `netval_plot`,
`asset_plot`, `buffer_plot`, `assetspie0/1`). Those series are exact per-month
ground truth and are stored as golden fixtures under `fixtures/`.

## Time grid

- Monthly steps. Age axis in years, step `1/12` (e.g. `36.67, 36.75, ...`).
- Simulation starts at the **current month** (a run on 2026-09 starts at 08/2026).
- Horizon ends at **age 81.0 — a fixed constant**, not gender- or cohort-derived:
  male and female, DOB 1990 and DOB 1980 all terminate at exactly 81.0.
- Chart arrays carry a duplicated first and last label (area-chart padding);
  real months = `(81 - age_now) * 12 + 1`.
- A person already past the max retirement age gets "no results".

## Money is REAL (today's shekels)

No inflation input exists anywhere in the form, and a flat 5,000 expense stays
5,000 for 44 years. The user's return inputs are therefore real returns. This
matches the convention already used by `backend/services/retirement_service.py`.

## Portfolio growth — exact formula

Verified to the shekel on three independent scenarios:

```
monthly_factor = ((1 + interest) * (1 - fee)) ** (1/12)
balance[t+1]   = (balance[t] + deposit[t]) * monthly_factor
```

- Fee and interest combine **multiplicatively**, not `interest - fee`.
  With i=10%, f=3% the observed monthly factor is `1.0054189`
  = `(1.10*0.97)^(1/12)` = 6.70% net, **not** `1.07^(1/12)`.
- Deposits land at the **start** of the month and grow that same month.
  Check: `(1_000_000 + 5_000) * 1.0039906 = 1_009_010.4` — matched exactly.
- With i=5%, f=0.1%: `(1.05*0.999)^(1/12) = 1.0039906`.

## Cash-flow routing (surplus)

Per month, `surplus = income - expenses`. Routing, in order:

1. Top the checking account up to `cashBuffer` (יתרת עובר ושב רצויה).
2. Deposit the rest into portfolios, in list order, subject to two caps:
   - `portfolio_deposit<i>` — monthly deposit cap (blank = unlimited);
   - `portfolio_goal<i>` — **target balance; deposits stop once reached**.
     `goal = 0` therefore means "never deposit" — the surprising default.
3. Anything left over accumulates in the checking account without return.

Evidence: with `goal=0` the whole 5,000/mo surplus piled up in cash (995,000 by
retirement, 0% growth); with `goal=9,000,000` the same surplus went entirely to
the portfolio and retirement moved 3.4 years earlier (53.2 → 49.8).
With `deposit=2,000` exactly 2,000/mo went to the portfolio and 3,000/mo to cash.

## Portfolio designation gates withdrawal eligibility

`portfolioDesignation`: `withdraw` (תיק משיכה למחיה) funds living expenses;
`goal` (תיק ליעדים) does **not** — a scenario with only a `goal` portfolio fails
to retire at all while that portfolio grows untouched to 7.9M.
Also `mukeret_main` / `mukeret_partner` (earmarked against the pension's
"recognised annuity" component) — not yet characterised.

## Capital gains tax is modelled

`portfolioProfitFraction` = share of the current balance that is unrealised
profit. It does not change accumulation (identical balances) but does change
the **gross withdrawal** needed to fund the same net expense, and therefore the
retirement date:

| profit fraction | retirement age | avg gross withdrawal |
|---|---|---|
| 0%  | 40.2 | 4,264.8 |
| 50% | 40.8 | 4,459.4 |
| 90% | 41.2 | 4,618.6 |

`portfolio_fifo_lifo` (`flat` / `fifo` / `lifo`) selects the lot-accounting
method. Exact rate and lot mechanics still to be pinned down.

## Bituach Leumi is auto-generated

Never entered by the user; the engine emits e.g. "ביטוח לאומי של T - זיקנה,
קצבה מגיל 67 בגובה 2,757.0 ₪". Women retire earlier in the model (52.7 vs 53.2
on an otherwise identical scenario), consistent with a lower BL eligibility age.
Derivation not yet characterised.

## Levers that did nothing (yet)

`retireRule` (85 → 95 → 100) changed nothing *visible* in a pension-free
scenario. **Superseded — see notes/05 §6:** it does change the return used in
the decumulation phase even in `baseline` (monthly factor 0.99993722 at 85 vs
0.99991933 at 100); it just failed to move the retirement date there because
`portfolio_goal1=0` routed the whole bridge through 0 %-return cash.

## The solver's search space (verified)

`retire_asap` scans candidate retirement months from now up to
`base_problem_max_age`, and the failure message quotes that bound verbatim:
`fixtures/desig_goal.json` reports "לא הצלחת להגיע ליעדיך בפחות מ **280** חודשים"
for a person aged 36.67 with `base_problem_max_age = 60` —
and `(60 − 36.67) × 12 = 280` exactly. So the search is over
`0 .. (max_retire_age − current_age) × 12` months, at monthly granularity, and
the answer is the earliest month that satisfies every goal.
