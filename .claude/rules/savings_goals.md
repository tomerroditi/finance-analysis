---
paths:
  - "backend/services/savings_goal_service.py"
  - "backend/routes/savings_goals.py"
  - "backend/models/savings_goal.py"
  - "frontend/src/components/dashboard/GoalsSection.tsx"
  - "frontend/src/components/budget/SavingsGoalsBudgetSection.tsx"
---
# Savings Goals — the surplus waterfall

How `backend/services/savings_goal_service.py` turns each month's leftover
money into goal progress. Read this before touching the service, the
`savings-goals` routes, `GoalsSection.tsx`, or the goals block on the monthly
budget view.

## A goal is an earmark, never an asset

A savings goal labels money that **already sits in tracked accounts**. It is
not a holding and it must never be added to net worth, the Sankey, or the
investments total — doing so would count the same shekel twice, the same trap
Keren Hishtalmut poses for the retirement calculator (see
`retirement_calculations.md`). Nothing outside the savings-goal service reads
goal balances today; keep it that way unless you also subtract the earmark from
the account it sits in.

## The monthly waterfall

For each month, from the earliest goal's `start_month` through the current one:

```
surplus    = income - expenses - investments     (realized, CC-deduped)
free_cash += surplus                             (the pool moves with the month)
pool       = max(0, surplus)
pool      -= frozen allocations of closed goals  (already spoken for)
pool      -= explicit contributions              (consume before the waterfall)
for each active goal, by priority ascending:
    take = min(target - funded, pool, monthly_cap or ∞)
    free_cash -= take
if free_cash < 0:                                (the month overspent)
    free_cash = 0
    for each active goal, by priority DESCENDING:
        give_back = min(funded - utilized, shortfall)
```

- **Surplus is realized, not forecast.** It comes from actual transactions,
  with credit-card and insurance rows excluded (the bank-side bill is the real
  outflow) and synthetic prior-wealth rows dropped — those are opening capital,
  and counting them would hand one month an enormous phantom surplus.
- **Investment transfers reduce the surplus.** Money moved into an investment
  has left the spendable balance the earmark sits over.
- **A negative month allocates nothing, and reaches the goals only last.**
  Overspending drains the free-cash pool first (below); a goal is only
  un-funded once that pool is empty.
- **`monthly_cap` is what stops a big goal starving the rest.** Uncapped, a
  priority-1 goal absorbs everything until it fills.
- **`start_month` gates participation**, so a goal created today cannot claim
  surpluses that predate it. It defaults to the creation month.

## The free-cash pool

The counterweight to the goals is `free_cash`: the tracked money no goal has
earmarked. It exists so an overspent month has somewhere to land before the
engine starts taking money back out of the goals.

- **It opens at the spendable money that existed when the first goal started** —
  bank + cash *prior wealth* (`_opening_free_cash`, investment prior wealth
  deliberately excluded: money in an investment is not free cash), plus every
  month of realized surplus that predates the walk, less the goals' opening
  balances. Anchoring on prior wealth alone would ignore all the history the
  goals never saw.
- **It moves with the whole month, not just the positive part.** The waterfall
  still only distributes `max(0, surplus)`, but the pool is credited with the
  surplus itself and debited for every shekel a goal takes out of it. What the
  goals do not claim simply stays in the pool.
- **It never goes negative.** An overspend the goals cannot cover came from
  money this model does not track (an overdraft, an untagged account); the pool
  floors at zero rather than carrying a phantom debt forward.
- **It is spendable cash, not a bank statement.** Investment transfers reduce it
  for the same reason they reduce the surplus, so it will sit below the raw
  bank + cash balance for anyone who invests.
- `free_cash + Σ available` is the liquid money the goals sit over, which is
  what `GET /savings-goals/free-cash` reports as `liquid`. That endpoint
  short-circuits to zeros when the user keeps no goals, so the no-goals path
  still pays for no transaction scan.

### Clawback: the waterfall in reverse

When a month's deficit outlives the pool, the shortfall comes back out of the
goals **lowest priority first** — the mirror image of funding, so the goal that
matters most is drained last.

- **A goal gives back at most `funded - utilized`.** Money already spent out of
  a goal is gone and can never be reclaimed; a goal with nothing available
  gives nothing. This is what makes tracking utilization load-bearing rather
  than merely informative.
- **A clawback is a negative `savings_goal_allocations` row** in the deficit
  month, so the ledger stays the single source of truth and `allocated` nets
  out on its own. `clawed_back` on the API payload sums those rows so the UI
  can show what was taken without reading the ledger itself.
- **Closed goals are never clawed back** — frozen means frozen, in both
  directions.
- **A history month's existing rows still stand.** The clawback obeys the same
  immutability rule as funding: only an explicit `rebuild` restates a month
  that already has rows. That is also why a plan's clawbacks cannot be read
  back off `_Plan` — a replayed history month computes nothing — so
  `get_month_allocations` and `get_free_cash` read them from the stored rows.
- **A replayed negative row must not refill the month's distributable pool.**
  It hands money back to `free_cash`, not to the waterfall; getting this wrong
  lets a deficit month fund a goal that had no row there yet.

## Every shekel is counted once

Transactions linked to a goal are **pulled out of the surplus calculation**
(`_compute_context`) and reintroduced explicitly:

| link | effect |
|---|---|
| `contribution` | credits the goal **and** consumes the pool before the waterfall |
| `utilization` | reduces the goal's `available`, leaves the pool alone |

A utilization does **not** reduce `target_amount` — buying the thing you saved
for is money *used*, not a smaller goal. And it must not reduce that month's
pool either: the money was set aside in an earlier month, so charging it again
would double-count it.

Leaving a linked transaction inside the surplus *and* deducting the
contribution from the pool is the bug this design exists to prevent; it nets to
the same total by deducting the same shekel twice.

A goal may also name a `contribution_category` (+ optional semicolon-separated
`contribution_tags`, the budget-rule convention) to accrue matching
transactions automatically. An explicit per-transaction link always wins over
the category rule, so one correction beats the broad match.

## History is never silently restated

Allocations persist per `(goal, month)` in `savings_goal_allocations`.

- `ensure_allocations()` fills in months with no rows and **always recomputes
  the current month**, which is provisional until it ends.
- A month already on record keeps its amounts. A goal added later may still
  draw on what that month left *unallocated* — that is additive backfill, and
  it never takes from a goal already funded there.
- Changing priorities applies **forward only**. Restating the past is an
  explicit `rebuild`, and the UI previews it with `dry_run=True` first.

### Closed goals are frozen

A goal auto-closes when it is achieved **and** fully utilized (`available <=
0`); it can also be closed by hand. Once closed:

- it stops absorbing surplus, and
- its allocations are **immutable** — a rebuild replays them and deducts them
  from the pool, so money can never be pulled back out of a goal that has
  already been spent.

This is why `rebuild` only ever deletes and recomputes rows for goals that are
not closed.

## Where the numbers surface

- **Dashboard** (`GoalsSection.tsx`) — the waterfall in priority order, with
  reorder arrows, `this_month_allocation`, `utilized`/`available`,
  `clawed_back`, the redistribute preview, and the free-cash pool on a dashed
  row below the goals (`GET /savings-goals/free-cash`, its own query key).
- **Monthly budget** (`SavingsGoalsBudgetSection.tsx`) — what each goal
  received that month, below the ledger rows. A deficit month reads in
  reverse: an amber banner explains the clawback and the per-goal rows go
  negative.

The budget block's data rides on `GET /budget/analysis/{year}/{month}` as a
`savings_goals` key, **not** its own request. It used to have one, and that
extra per-month call added another straggler to every refresh of the same
screen, pushing the budget page's post-mutation refresh past the deadline the
`budget-create-rule` e2e allows. `GET /savings-goals/allocations/{y}/{m}` still
exists for direct callers and tests; don't wire the budget page back onto it.

Relatedly, `get_month_allocations` short-circuits before touching transactions
when the user has no goals, and `_build_context` is memoised per service
instance (one request needs it twice — allocating, then enriching). Both exist
so the many users who keep no goals pay nothing for the section.

## Gotchas

- `SavingsGoal.status` / `is_achieved` / `is_closed` arrive from SQLite as
  0/1 integers. Guard them with `!!` in JSX — `{0 && <Check/>}` renders a
  literal "0" beside the goal name (there is an e2e pinning this).
- The frozen demo snapshot is schema-synced by `demo_setup.py`, which only ever
  *adds* columns. A retired `NOT NULL` column left behind breaks every ORM
  insert into that table, so `RETIRED_COLUMNS` drops it — that is why
  `savings_goals.current_amount` is listed there.
- The redistribute preview is a POST that changes nothing. Keep it a
  **mutation**, not a query: as a query its key sits under the `savings-goals`
  prefix, so every goal mutation re-triggers it, and the IndexedDB persister
  would cache a read-only POST (see `frontend_pwa.md`).
