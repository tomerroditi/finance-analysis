# Cash flows, timing enums, debt, real estate, checking account

Companion to `01-fundamentals.md` (time grid, portfolio growth, surplus
routing). Everything below was measured against the live calculator; 14
probes, all saved under `fixtures/cf_*.json`. "Verified to the shekel" means a
predicted number matched the returned series exactly at the precision the
chart carries (1 decimal).

## 0. Index mapping used throughout

Chart arrays have 535 entries with a duplicated first and last label. For a
run made on 2026-09:

```
data[0]                = padding (always 0)
data[i], i = 1..533    = calendar month 2026-09 + (i-1)
data[534]              = padding
```

Verified on `baseline`: `labels[199] = 53.17`, and the summary says the
retirement month is 03/2043 — 2026-09 + 198 months = 2043-03, and a person born
1990-01 is 53 y 2 m = 53.167 then. The "current point in time" shown in the
summary (08/2026) is the month *before* `data[1]`; opening balances are stated
as of that month.

**Everything is month-granular; the day component of every date input is
ignored.** Proven for `from_date`/`to_date` (`cf_timing_bits`, days 15 / 28 /
01 all behave identically), for `debtStartDate` (`cf_loan_edge`, day 20 behaves
exactly like day 01) and for `dateOfBirth` (`cf_dob_midmonth`, DOB 1990-01-20
produces the identical age axis and the identical age-60 boundary as
1990-01-01).

## 1. Start × end timing enums

Method: `cf_timing_bits` keeps the baseline 5,000 expense / 10,000 income rows
and adds eight extra expense rows and eight extra income rows whose amounts are
1, 2, 4, …, 128, each with a different start×end combination. The month-by-month
total therefore bit-encodes exactly which rows are live. FIRE landed on
04/2043 = index 200.

Observed `הוצאות שוטפות` minus the 5,000 carrier (`cf_timing_bits`):

| index | month | bits | decoded |
|---|---|---|---|
| 1–45 | 2026-09 … 2030-05 | 7 | now→fire, now→to_date(2030-06-15), now→60 |
| 46 | 2030-06 | 15 | + from_date(2030-06-15) joins **in the month of its date** |
| 47 | 2030-07 | 13 | to_date(2030-06-15) row gone — **end month inclusive** |
| 80 | 2033-04 | 77 | + from_date(2033-04-**28**) joins in 2033-04 |
| 104 | 2035-04 | 13 | to_date(2035-03-**01**) row gone after 2035-03 |
| 200 | 2043-04 (FIRE) | 13 | now→fire **still live in the FIRE month** |
| 201 | 2043-05 | 156 | now→fire gone; fire→forever and fire→60 **start the month after FIRE** |
| 282 | 2050-02 | 24 | both `60` rows gone after 2050-01 |

### Rules (all verified to the shekel)

- **`now`** — first simulated month (2026-09), inclusive.
- **`from_date D`** — from the calendar month of `D`, inclusive. A `D` in the
  past means "from the first simulated month": income row 4 (`from_date
  2020-01-15`, amount 4) is live from index 1 (`cf_timing_bits`, work income
  = 10,037 = 10,000+1+4+32 in 2026-09).
  A `D` near the end still works: income row 8 (`from_date 2069-01-15`, amount
  64) turns on at index 509 = 2069-01 (work income 6 → 70).
- **`to_date D`** — through the calendar month of `D`, inclusive.
- **`forever`** — through the last simulated month (index 533 = 2071-01,
  age 81.0), inclusive. `cf_dob_midmonth` income row `from_date 2071-01-05`
  is live in exactly that last month (work = 4 at index 533).
- **`60`** — through the month in which the **main** retiree turns 60,
  inclusive. DOB 1990-01 → 2050-01 = index 281 is the last live month, index
  282 is the first dead one. Confirmed for DOB 1990-01-20 as well
  (`cf_dob_midmonth`: 5,001 through index 281, 5,000 from index 282).
- **`fire`** — `end=fire` includes the FIRE month; `start=fire` begins the
  month **after** the FIRE month. Exactly one month partition, no overlap and
  no gap (indices 200 / 201 above).
- **`one_time`** — a single month, taken from the row's **start date**, and the
  end type is ignored. It is charted in a *separate* dataset: expenses go to
  `יעדים` ("goals"), incomes to `הכנסות חד פעמיות`. `cf_timing_bits` expense
  row 7 (`one_time 2032-11-01`, amount 32) appears only at index 75 = 2032-11
  in `יעדים`; income row 5 (`one_time 2032-11-01`, amount 8) appears only at
  index 75 in `הכנסות חד פעמיות`. Income row 5 had `end=fire` and income
  row 6 had `end=forever` — both behaved as a single month, so the end type is
  inert for `one_time`.
- **A `one_time` dated in the past is dropped entirely.** Income row 6
  (`one_time 2020-05-01`, amount 16) never appears anywhere in the series.
- **An empty range is dropped.** Income row 9 was `fire → to_date 2040-01-15`
  with FIRE at 04/2043, i.e. the end precedes the start; the post-FIRE work
  income is 6 = 2+4, with bit 128 absent everywhere. No error, just nothing.

### The `fire` anchor while the solver is still searching

This is self-consistent, not a stale first guess.

- `cf_fire_split` splits the baseline's single `5000 now→forever` expense into
  `5000 now→fire` + `5000 fire→forever`, changing nothing else. The result is
  **bit-for-bit identical to `baseline`** — same 03/2043 retirement month, and
  `max|Δ| = 0.0` on every dataset of `expense_plot`, `income_plot`,
  `netval_plot` and `asset_plot`. The solved date is a genuine fixed point of
  the flows anchored to it.
- `cf_postfire_surplus` adds a `20,000 fire→forever` income to the baseline.
  The solver moves retirement all the way to **09/2026 — the first simulated
  month** (index 1): work income is 10,000 at index 1 (the `now→fire` row)
  and 20,000 from index 2 onward. A fire-anchored flow therefore feeds back
  into the search rather than being evaluated once.
- **When no retirement date is feasible**, `fire` resolves to the month of
  `base_problem_max_age`. In `cf_rise` the run reports "could not reach your
  goals in fewer than 280 months" and pins the snapshot at 01/2050 (= age 60,
  the `base_problem_max_age`), and the `fire→forever` expense row starts at
  index 282 = 2050-02, i.e. the month after, by the normal rule.

## 2. `expenseRise` / `incomeRise`

**Monthly compounding of the annual rate, anchored at the row's own first
active month.**

```
amount(month m) = sum * (1 + rise) ** ((m - first_active_month_of_this_row) / 12)
```

Evidence (`cf_rise`: expense row 1 = 5,000 `now→forever` rise 3 %, expense row
2 = 1,000 `from_date 2030-06-15` rise 3 %, expense row 3 = 1,000
`fire→forever` rise 3 %, income row 1 = 12,000 rise 2 %):

- Not an annual step: index 1 = 5,000.0, index 2 = **5,012.3** =
  5,000·1.03^(1/12) = 5,012.33. Income index 2 = **12,019.8** =
  12,000·1.02^(1/12) = 12,019.82.
- Exactly annual after 12 months: index 13 = **5,150.0** = 5,000·1.03, income
  index 13 = **12,240.0** = 12,000·1.02.
- Anchored per row, not to "today": at index 46 (2030-06, row 2's first month)
  the total is 6,586.1; row 1 alone predicts 5,000·1.03^(45/12) = 5,586.14, so
  row 2 contributes exactly **1,000.0** — its base, un-risen. At index 47 row 2
  contributes 1,002.5 = 1,000·1.03^(1/12).
- Also anchored per row for a `fire` start: FIRE is 01/2050 (index 281), and at
  index 282 the residual after subtracting rows 1 and 2 is **999.98 ≈ 1,000.0**;
  at index 300 it is 1,045.38 vs the predicted 1,000·1.03^(18/12) = 1,045.34.
  (The alternative "rise from today" would give 1,998 and 2,088.)

Since the whole model is in real terms, this is a real rise.

Not tested: `rise` on a `one_time` row (its own start is its only month, so it
should be inert), and negative `rise`.

## 3. Multiple income / expense rows

Add rows by bumping `num_expense_fields` / `num_income_fields` and posting
`expenseSum2`, `expenseStartType2`, … (`mk.py` in this directory builds them).
The `add_line` endpoint is not required — the server just reads the counter.
Confirmed working with 9 expense rows and 9 income rows in one submission
(`cf_timing_bits`).

Rows are **summed** into one charted series per class:

- all non-`one_time` expense rows → `הוצאות שוטפות`
- all `one_time` expense rows → `יעדים`
- all non-`one_time` income rows → `עבודה`
- all `one_time` income rows → `הכנסות חד פעמיות`

There is no per-row series; `expenseDescription` is not used as a dataset
label.

## 4. THE MYSTERY: `הוצאה לא מתוכננת` ("unplanned expense")

**It is the monthly increase in the checking account — the part of the surplus
that has nowhere planned to go.** The label is simply wrong/misleading.

The baseline is degenerate: income 10,000 − expense 5,000 = surplus 5,000,
which happens to equal the expense, so the series looks like a mirror of the
expense series. It is not.

Verified to the shekel:

- `baseline` and `cf_timing_bits`: for every index 2…199, `cash[i] − cash[i-1]`
  (the `עובר ושב` series in `asset_plot`) equals `הוצאה לא מתוכננת[i]` — **0
  mismatches**. Samples from `cf_timing_bits`: (5,030.0 / 5,030.0),
  (4,992.0 / 4,992.0), (4,968.0 / 4,968.0).
- At index 75 of `cf_timing_bits` the value 4,968 = (work 10,005 + one-time
  income 8) − (ongoing expense 5,013 + one-time expense 32). One-time rows are
  included in the arithmetic.
- It is not "surplus before retirement": in `cf_postfire_surplus` (FIRE at the
  first month) it reads 15,000 for the whole post-retirement period
  (20,000 − 5,000) and 17,911.5 at index 533 once the 2,911.5 old-age pension
  starts.
- It is not "the deposit into portfolios": in `cf_rise`, where
  `portfolio_goal1 = 9,000,000` so the surplus is actually invested, the
  `הוצאה לא מתוכננת` dataset **is absent entirely** and a
  `הפקדה לתיק בברוקר בארץ` dataset carries the same numbers instead
  (index 1: income 12,000 − expense 5,000 = deposit 7,000.0, checking flat at
  0 for the whole run). The reason the baseline shows it at all is the
  `portfolio_goal1 = 0` default, which blocks all deposits and forces the
  surplus into cash.

### The full `expense_plot` decomposition

`expense_plot` is really "where the month's money went". Datasets seen:

| dataset | meaning |
|---|---|
| `הוצאות שוטפות` | recurring expense rows, summed |
| `יעדים` | one-time expense rows |
| `הלוואות` | loan payments |
| `הפקדה לתיק <name>` | deposit into that portfolio |
| `מס על רווחי תיק <name>` | capital-gains tax on that portfolio's withdrawal |
| `הפרשה לעובר ושב` | repayment of an overdrawn checking account |
| `הוצאה לא מתוכננת` | leftover piling up in the checking account |

`הפרשה לעובר ושב` verified on `cf_credit_100k`: nonzero only for indices
41–55, exactly while the overdraft is being repaid; at index 55 it is 407.5 and
`הוצאה לא מתוכננת` is 4,592.5, summing to the 5,000 surplus, and the checking
balance crosses from −407.5 to +4,592.5.

Correspondingly `income_plot` gains `החתיכה החסרה` ("the missing piece") when
the plan cannot fund a month — see §7.

## 5. Loans

Loan rows use `debtStartDate<i>`, `debtInterest<i>` (annual %),
`debtInitialSum<i>`, `debtTotalPeriod<i>` (years), `debtType<i>`, with
`num_loan_fields`.

Common to all three types, verified on `cf_loan_spitzer`, `cf_loan_baloon_grace`,
`cf_loan_over_fire`, `cf_loan_edge`:

- **Monthly rate is nominal: `r = annual / 12`**, not `(1+annual)^(1/12) − 1`.
  With 5 %: r = 0.00416667. (The portfolio side uses geometric monthly
  compounding — the two conventions differ inside the same engine.)
- **`n = 12 × debtTotalPeriod` payments, made in months `start+1 … start+n`.**
  No payment in the start month itself: in `cf_loan_spitzer` the `הלוואות`
  series is 660.0 at index 1 (the 2016 loan only) and 2,639.8 from index 2
  (both loans).
- `loan_plot[i]` is the outstanding balance at the **end** of month i.
- **Loan payments are cash-flow expenses.** They reduce the surplus:
  `cf_loan_spitzer` index 1, 10,000 − 5,000 − 660.0 = 4,340.0 =
  `הוצאה לא מתוכננת[1]` = the checking balance at index 1. They are charted in
  their own `הלוואות` dataset, not inside `הוצאות שוטפות`.
- **Net worth subtracts the outstanding balance every month**, not only at
  retirement. `cf_loan_spitzer`: `netval[i] == cash[i] + portfolio[i] −
  loan1[i] − loan2[i]` at every index checked (1, 2, 100, 200, 241, 242, 300),
  e.g. index 1 = −257,482.4 with assets 104,739.0 and debt 362,221.5.
  Same identity holds in `cf_loan_baloon_grace`.
- **A loan is not repaid at retirement in cash-flow terms.**
  `cf_loan_over_fire` (500,000, 5 %, 40 y, start 2026-09; retirement pinned at
  01/2050 = index 281) keeps paying 2,411.0 every month from index 2 to index
  481 = 2066-09, straight through retirement, and the balance keeps amortizing
  (index 281 = 326,726.0, index 300 = 306,017.4). The summary's retirement
  snapshot reports `התחיבויות 326,726` — the outstanding balance at that month.
  So the site's assumption text ("loans are subtracted from net worth, as if
  repaid in full on retirement day") describes the **net-worth display only**;
  the simulated cash flow keeps servicing the loan.
- **A loan that started in the past is amortized forward from its true start
  date**, and only the remaining schedule is simulated. `cf_loan_spitzer` loan 2
  (100,000, 5 %, 20 y, start 2016-09): predicted balance after 119 payments
  (through 2026-08) = **62,620.56**, and the summary reports
  `התחיבויות 62,621` at 08/2026; predicted after 120 payments = **62,221.52**,
  observed `loan_plot[1] = 62,221.5`. Its last payment is at index 121 =
  2036-09 = start + 240 months.
- **A loan whose original term already ended is dropped entirely.**
  `cf_loan_edge` loan 1 (start 2010-01-15, 10 y, i.e. finished 2020-01) produces
  no series, no payment and no liability — only `הלוואה 2` appears, and net
  worth at 08/2026 is the clean 100,000.

### spitzer (equal payment)

```
A     = P * r / (1 - (1+r)**-n)
B_k   = P*(1+r)**k - A*((1+r)**k - 1)/r          # after k payments
```

`cf_loan_spitzer`, P = 300,000, i = 5 %, n = 240:
predicted A = **1,979.8672**; observed payment (2,639.8 total minus the second
loan's 659.9557) = 1,979.85, and after the second loan ends the series reads
exactly **1,979.9**. Balances matched at every index tested:
index 2 obs 299,270.1 / pred 299,270.13; index 60 obs 251,297.4 / pred
251,297.38; index 120 obs 187,861.7 / pred 187,861.67; index 240 obs 1,971.7 /
pred 1,971.65 (= A/(1+r), the balance before the final payment); index 241 = 0.

`cf_loan_edge`, P = 120,000, i = 5 %, n = 120: predicted A = **1,272.79**,
observed 1,272.8, first payment index 2, last index 121.

`cf_loan_over_fire`, P = 500,000, i = 5 %, n = 480: predicted A = **2,410.98**,
observed 2,411.0, constant for all 480 payments.

### baloon (balloon)

**No payments at all; interest capitalizes monthly; one payment of
`P*(1+r)**n` in month `start+n`.**

```
balance[i] = P * (1+r)**(i-1)          (for a loan starting at index 1)
payment    = P * (1+r)**n              in month start+n, nothing before
```

`cf_loan_baloon_grace` loan 1, P = 200,000, i = 5 %, 15 y (n = 180), start
2026-09: balance index 2 obs 200,833.3 / pred 200,833.33; index 60 obs
255,606.7 / pred 255,606.71; index 180 obs 420,986.7 / pred 420,986.68. The
`הלוואות` series is 0 for the balloon until index 181 = 2041-09, where it jumps
to **422,740.8** against a predicted 200,000·(1+r)^180 = **422,740.79**, then 0.
Net worth carries the accreting balance the whole time (identity checked at
indices 1, 2, 100, 181, 182).

### grace

**Interest-only; the principal is repaid as a bullet with the last payment.**

```
payment[m] = P * r                     for m = start+1 .. start+n-1
payment[start+n] = P * r + P
balance    = P, unchanged, until it drops to 0 at start+n
```

`cf_loan_baloon_grace` loan 2, P = 100,000, i = 5 %, 10 y (n = 120), start
2026-09: the `הלוואות` series is **416.7** (= 100,000·0.05/12 = 416.667) from
index 2 through index 120, then **100,416.7** at index 121 = 2036-09, then 0.
`loan_plot` shows a flat 100,000.0 for indices 1–120 and 0 from 121.

Note this is *partial* grace (Israeli "גרייס חלקי") — interest is serviced, not
capitalized, which is what distinguishes it from `baloon`.

Open question: whether `debtInterest` is ever treated as anything other than a
plain nominal annual rate divided by 12 (e.g. a prime-linked or CPI-linked
loan). Nothing in the form suggests it, and all three types matched the plain
nominal convention exactly.

## 6. Real estate

`realestateValue<i>`, `realestateRise<i>`, `num_realestate_fields`.

- **It enters net worth and it appreciates**, monthly-compounded like the flow
  rise: `value[i] = V0 * (1+rise)**(i/12)` (i = 1 for the first simulated month) —
  note it already grows in the **first** month, unlike an expense row, whose
  first month is un-risen. `cf_realestate` (1,000,000 @ 3 %):
  index 1 = **1,002,466.3** = 1,000,000·1.03^(1/12) = 1,002,466.27; index 13 =
  1,032,540.3 = 1,000,000·1.03^(13/12) = 1,032,540.2; index 533 = 3,716,950.1
  vs 1,000,000·1.03^(533/12) ≈ 3,716,979 (agreement to ~8 significant digits;
  the tiny gap is repeated float multiplication by the monthly factor).
- Net worth includes it exactly: `netval[1] = 1,107,865.3 = cash 5,000 +
  property 1,002,466.3 + portfolio 100,399.0`. It also appears in both
  doughnut charts (`assetspie0` = [100,000 portfolios, 1,000,000 real estate]).
- **It produces no rent and is never liquidated.** `cf_realestate` retires on
  **03/2043 — exactly the baseline date** despite adding 1 M of "assets", and
  at the end of the horizon the portfolio has run down to 6,966.2 while the
  property still sits at 3,716,950.1 untouched.
- The sharpest test is `cf_re_no_rescue`: it repeats the failing `cf_credit_0`
  scenario with a 2,000,000 property (rise 0) bolted on. The property is worth
  2,000,000 at index 1, 100 and 533 — never sold — and the shortfall series
  `החתיכה החסרה` and the checking series are **bit-identical to `cf_credit_0`**
  (`max|Δ| = 0.0`, total shortfall 70,407.5 in both). Real estate cannot rescue
  a plan; it is display-only net worth.

Open question: whether a real-estate row interacts with anything at all besides
the net-worth line and the pies (e.g. a mortgage attached to it) — nothing in
the input surface links loans to properties.

## 7. `balance`, `cashBuffer`, `creditLimit`

- **`balance`** is the checking balance as of the "current" month (08/2026),
  before the first simulated month. `cf_credit_100k` sets `balance = 25,000`
  with a 5,000/mo deficit; the `buffer_plot` reads 20,000 at index 1, 15,000 at
  index 2, …, 0 at index 5. The summary's opening net worth is
  125,000 = 25,000 + 100,000.
- **`cashBuffer`** is the desired checking balance; the surplus tops it up
  before anything is deposited into portfolios (already in `01-fundamentals`).
  `buffer_20k` (buffer 20,000, balance 20,000, `portfolio_goal1` 9,000,000)
  holds the checking at exactly 20,000.0 for the entire run.
- **Withdrawal order at a deficit: checking first, portfolios second.**
  `cf_credit_100k`: indices 1–5 draw 5,000/mo from `משיכה מעובר ושב` while the
  portfolio keeps growing (100,399.0 → 102,011.2); only at index 6, with the
  checking at 0, does `משיכה מתיק` start (5,024.8 — grossed up for capital-gains
  tax, see `01-fundamentals`).
- **`creditLimit` is a hard floor at `-creditLimit` on the checking account.**
  Three runs of the identical scenario (balance 25,000, no income until
  2030-01, 5,000/mo expense, 100,000 portfolio):

  | fixture | creditLimit | min checking | shortfall (`החתיכה החסרה`) |
  |---|---|---|---|
  | `cf_credit_100k` | 100,000 | **−70,407.5** (index 40) | none — plan succeeds, retires 04/2047 |
  | `cf_credit_30k` | 30,000 | **−30,000.0** exactly | 407.5 at index 32 then 5,000/mo, 9 months, total 70,407.5 |
  | `cf_credit_0` | 0 | **0.0** | 407.5 at index 26 then 5,000/mo, 15 months, total 70,407.5 |

  The 407.5 first-shortfall figure is the exact residual left over the month the
  portfolio is exhausted, and it is identical in all three runs — the engine
  simulates the same cash flow and only clips it at a different floor.
- **An unfunded month is reported, not accrued.** In `cf_credit_0` the checking
  sits at 0 through the shortfall and then jumps to +5,000 the month income
  resumes (index 41) — the 70,407.5 of unpaid expenses is never carried as
  debt. In `cf_credit_30k` the overdraft stays at −30,000 and is then repaid
  from surplus (−25,000 at index 41, −20,000 at index 42), again without the
  clipped amount being added.
- A negative checking balance is repaid out of the surplus before anything else
  and is charted as `הפרשה לעובר ושב` (see §4).

Open question: whether the checking overdraft bears interest. Over indices 26–40
of `cf_credit_100k` the balance moves in exact −5,000.0 steps from −407.5 to
−70,407.5 with no interest accretion, so **within this probe the overdraft is
free** — but there is no input for an overdraft rate, so this is likely by
design rather than an artifact.

## Fixture index

| fixture | what it establishes |
|---|---|
| `cf_timing_bits` | all start×end enum combinations, month boundaries, one-time semantics |
| `cf_rise` | monthly compounding of `rise`, per-row anchor, `fire`-anchored rise, failed-plan behaviour |
| `cf_fire_split` | `now→fire` + `fire→forever` == `now→forever`, bit-for-bit |
| `cf_postfire_surplus` | fire-anchored income feeds the solver; `הוצאה לא מתוכננת` post-FIRE |
| `cf_loan_spitzer` | spitzer amortization, past-start loan, loan payment as expense, net-worth identity |
| `cf_loan_baloon_grace` | balloon capitalization + bullet; grace interest-only + bullet |
| `cf_loan_over_fire` | loan payments continue past retirement; liability shown at retirement |
| `cf_loan_edge` | expired loan dropped; `debtStartDate` day ignored |
| `cf_realestate` | appreciation formula, net-worth inclusion, no effect on retirement date |
| `cf_re_no_rescue` | real estate never liquidated even when the plan fails |
| `cf_credit_100k` / `cf_credit_30k` / `cf_credit_0` | checking-first drawdown, `-creditLimit` floor, shortfall reporting |
| `cf_dob_midmonth` | month-granular DOB, age-60 boundary, horizon-last-month inclusion |
