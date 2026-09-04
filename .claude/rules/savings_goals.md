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
surplus = income - expenses - investments        (realized, CC-deduped)
pool    = max(0, surplus)
pool   -= frozen allocations of closed goals     (already spoken for)
pool   -= explicit contributions                 (consume before the waterfall)
for each active goal, by priority ascending:
    take = min(target - funded, pool, monthly_cap or ∞)
```

- **Surplus is realized, not forecast.** It comes from actual transactions,
  with credit-card and insurance rows excluded (the bank-side bill is the real
  outflow) and synthetic prior-wealth rows dropped — those are opening capital,
  and counting them would hand one month an enormous phantom surplus.
- **Investment transfers reduce the surplus.** Money moved into an investment
  has left the spendable balance the earmark sits over.
- **A negative month allocates nothing and never claws back.** Overspending
  does not un-fund a goal.
- **`monthly_cap` is what stops a big goal starving the rest.** Uncapped, a
  priority-1 goal absorbs everything until it fills.
- **`start_month` gates participation**, so a goal created today cannot claim
  surpluses that predate it. It defaults to the creation month.

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
  reorder arrows, `this_month_allocation`, `utilized`/`available`, and the
  redistribute preview.
- **Monthly budget** (`SavingsGoalsBudgetSection.tsx`) — what each goal
  received that month, below the ledger rows.

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
