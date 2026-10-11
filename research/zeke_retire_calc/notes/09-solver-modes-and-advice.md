# The four solver modes, and the "smart advice" optimiser

## `retire_asap` (פרישה מוקדמת) — the default
Searches monthly for the earliest feasible retirement, over
`0 .. (max_retire_age − current_age) × 12` months (see notes/01).
Failure text quotes that bound: "לא הצלחת להגיע ליעדיך בפחות מ 280 חודשים".

## `retire_at_age` (צ׳ק-אפ) — check-up at a fixed age
Pins retirement to `wanted_retire_age` and reports whether the plan holds.
`fixtures/sol_at_age_58` succeeds; `fixtures/sol_at_age_45` fails with a
*different* message — "לא הצלחת להגיע ליעדיך." with no month count — and still
returns the full projection, with the goal checklist showing which goal broke:
`X יעד כיסוי של הוצאות מחיה: כישלון`. So failure is per-goal, not global.

## `improve_cash_to_reach_retire_at_age` and `increase_risk_to_reach_retire_at_age`
**Both are broken in the live reference.** Every attempt returns
"אין תוצאות להצגה" and a server-side traceback:

```
File "/app/calculators/retirement.py", line 307, in calc_retirement
  income = OneTimePayment(expenseStartDate=None, expenseEndDate=None,
      expenseStartType="now", expenseEndType="fire", value=0, expenseRise=0,
      expenseDescription="", repetitions=None, interval=None)
TypeError: OneTimePayment() takes no arguments
```

Reproduced with two different parameter sets (`fixtures/sol_improve_cash`,
`sol_increase_risk`, `sol_improve_cash_alt`), so it is unconditional, not an
artefact of our inputs — the class is missing a constructor, so the code path
cannot ever have run.

**Consequence for us:** these two modes cannot be reverse-engineered from
behaviour, because they have no behaviour. We have to implement them from
intent: search the smallest monthly cash-flow improvement (bounded by
`base_problem_cash_improve`), or the smallest return increase (bounded by
`base_problem_risk_increase`), that makes `wanted_retire_age` feasible. That is
an inference, and it should be flagged as such rather than presented as parity.

### Bonus: the traceback leaks the reference's internals
- The engine is `/app/calculators/retirement.py`, entry `calc_retirement(is_extra=...)`.
- Cash flows are objects taking `expenseStartDate`, `expenseEndDate`,
  `expenseStartType`, `expenseEndType`, `value`, `expenseRise`,
  `expenseDescription`, **`repetitions`**, **`interval`**.
  The last two are *not exposed in the public form* — the internal model
  supports recurring one-time payments that the UI cannot express.

## The smart-advice optimiser

Two-stage protocol against the same endpoint. The first response carries a
`smart_advice` token; the page replays the identical form with that token set,
and the second response carries an `extra_status`.

A real token (`fixtures/sol_smart_advice`, from a plan whose only portfolio was
`goal`-designated so nothing could fund living costs):

```
open_living_portfolio@interest=5@reason=no_living_portfolio
  @portfolio_deposit=None@portfolio_subtype=auto_broker
  ,missing_piece,2129420.800086609
```

So the token is `action@key=value@...,<diagnosis>,<gap size>`. Here: open a
withdrawal portfolio at 5%, because there is none, and the shortfall is
2,129,420.8.

`extra_status.extra_status` is one of `not_done`,
`success_but_extra_not_beneficial` ("המלצות מערכת לא קידמו אותך"), or
`improved_amazingly`, which reveals a third results tab.

The advice output is rendered as a dated "event": *"Event 1: opening a
self-managed investment portfolio (system recommendation), proposed execution
date 09/2026"* — and, worth noting, it is also an **affiliate funnel**: the
recommendation body links to broker sign-up offers. We reproduce the mechanism,
obviously not the referrals.

## Two more output details this uncovered
- Each portfolio carrying a goal gets its **own** attainment row:
  `X תיק בברוקר בארץ: כישלון`.
- The failure narrative quantifies the shortfall:
  "קיים פער בכיסוי הוצאות מחיה של 175,546.8 ₪".
