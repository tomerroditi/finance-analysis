---
paths:
  - "backend/services/savings_goals/**/*.py"
  - "backend/routes/savings_goals.py"
  - "backend/models/savings_goal.py"
  - "frontend/src/components/dashboard/GoalsSection.tsx"
  - "frontend/src/components/dashboard/YearlySavingsSection.tsx"
  - "frontend/src/components/budget/SavingsGoalsBudgetSection.tsx"
  - "frontend/src/components/budget/BudgetGoalLink.tsx"
  - "frontend/src/components/dashboard/GoalAutoLinkField.tsx"
  - "frontend/src/components/dashboard/goalHistoryRows.ts"
  - "frontend/src/components/dashboard/GoalsHistoryPanel.tsx"
  - "frontend/src/components/dashboard/GoalEditorModal.tsx"
---
# Savings Goals — money you set aside, and the free cash beside it

How the `backend/services/savings_goals/` package works. `SavingsGoalService`
(`core.py`) assembles mixins: `inputs` (goal order and everything read off
transactions), `ledger` (each goal's balance and free cash, month by month),
`goals` (CRUD, money in and out, fund, cover, links), `read_models` (the goal
list, free cash, timeline and the budget month view) and `yearly` (this
year's savings against its target, below); `common` holds the month helpers
and `ROUNDING_EPSILON`. Read this before touching the service, the
`savings-goals` routes, `GoalsSection.tsx`, or the goals block on the monthly
budget view.

## The model in one paragraph

A goal holds **the money you put into it** (`savings_goal_entries`: dated,
signed — "Add money" is positive, "Take out" negative), **plus the income its
saved-into rule or income links claim, less the spending its spending rule or
links pay for**. **Free cash** is what the bank and cash accounts hold, less
everything the goals hold. Nothing is distributed automatically and nothing
ever restates the past: a goal's balance changes only because you moved money
or because a transaction you tied to it happened.

This replaced (2026-10, migration `31ce8f3f673d`) an automatic surplus
waterfall: each month's leftover money flowed down the goals by priority,
deficits clawed it back lowest-first, and any edit restated history. Every
rule it needed to stay consistent (bridges, fronted/released income, floors,
negative pools, restated ledgers) produced numbers the user could not
explain. Don't bring any of it back. If a goal's number needs explaining,
the explanation must be an entry or a transaction.

## A goal is an earmark, never an asset

A goal names money that already sits in the tracked bank and cash accounts.
It never adds to net worth, and investments are not part of it — goals are
**cash earmarks only** (investment goals were removed in `2a03db5febd7`).
Moving money into an investment is ordinary spending as far as free cash is
concerned: the bank balance drops.

## What a goal holds

`ledger.py` replays three kinds of dated event per goal, in date order
(same day: entries, then income, then spending):

| Event | Source | Effect |
|---|---|---|
| entry | `savings_goal_entries` (`manual`, `cover`, `close`, `migrated`) | `added += amount` |
| income | the goal's saved-into rule (`contribution_category` + tags) or a contribution link | `income += amount` |
| spending | the goal's spending rule (`utilization_category` + tags) or a utilization link | `spent += amount` (refunds net) |

`balance = added + income - spent`; `available = max(0, balance)` is what it
holds; `saved = added + income` is progress toward the target (spending
never shrinks progress or the target); `owed = max(0, -balance)`.

Two rules decide what a goal pays:

- **A goal with income of its own** (a saved-into rule or any income link)
  may spend ahead of that income. Its balance goes negative — `owed` — and
  the income repays it as it lands. Wedding bills before the gifts are a loan
  from free cash, not an overspend.
- **Any other goal** pays only with what it holds. A bill beyond that comes
  out of free cash for good: the balance stops at zero and `spent` counts
  only what the goal actually paid. A later deposit is new money, not a
  repayment.

Rules and links claim transactions from the goal's `start_month` through its
`closed_month` (inclusive) — `InputsMixin._claim_span`. Card purchases can be
paid out of a goal like bank rows. Only **incoming** money can be a
contribution link (`link_transaction` 400s on an outgoing one): setting money
aside is an entry, never a link on a transfer.

## Free cash

`liquid` at a month's end = bank + cash prior wealth + every bank and cash
transaction up to then (`_opening_liquid` + `context["liquid"]`); free cash
= liquid − Σ `available`. It can go **negative** — goals hold more than there
is — and the card shows it red with the shortfall.

Nothing covers a shortfall on its own. `cover_plan()` proposes taking it back
from the goals **lowest in the list first**, each giving at most what it
holds; `POST /free-cash/cover` applies it as `cover` entries after the user
confirms. Waiting for income is the other way out — next month's salary
raises liquid and closes the hole without touching any goal.

## Funding suggestions

A goal's `monthly_amount` is how much the user means to put in each month
(not a cap). `suggested_this_month = min(remaining, max(0, base -
added_this_month))`, where `base` is `monthly_amount`, or — without one —
what the target date needs per month as it stood before this month's
deposits (so funding it doesn't shrink the suggestion twice). Closed and
achieved goals suggest nothing. `POST /fund` (some goals, or `null` for all)
puts the suggestions in **top of the list first, never past free cash**: once
free cash runs out, the goals below get nothing rather than driving it
negative.

Priority (list order, reorder arrows) decides only two things: the order
"fund all" funds in and the reverse order a cover plan takes money back. It
never touches the past.

## Target date, start date, closing

- The **target date is a deadline**, not a window: a goal past it and still
  short keeps its balance and says so (`is_past_due`, "short · target date
  passed") instead of asking for "X/mo for 0 mo". `monthly_needed` sizes the
  remaining amount off the runway in **days** (`DAYS_PER_MONTH`), not
  calendar months.
- The **start month** bounds what the goal's rules and links claim; entries
  can be dated anywhere.
- **Closing** hands what the goal still holds back to free cash as a `close`
  entry and stops its rules after that month; **reopening** deletes the
  `close` entries, restoring exactly that money. Money cannot move into or
  out of a closed goal.
- **Deleting** a goal drops its entries and links: what it held is free cash
  again.

## Where the numbers surface

- **Dashboard** (`GoalsSection.tsx`) — "This year" savings on top
  (`YearlySavingsSection`), then the goals in list order with their balance,
  progress, add/take-out, a "Fund ₪X" chip when there is a suggestion, and
  an expandable entry list with undo; then the free-cash row (red with a
  "Cover it" button when negative, which confirms the plan first). The goal
  editor is `GoalEditorModal.tsx`. The goal list **scrolls in place** past
  ~26rem only once the cap hides about a row (`useScrollCap`;
  `frontend_pitfalls.md` → "Capped Scroll Regions").
- **Month by month** (`GoalsHistoryPanel.tsx`, rows from `goalHistoryRows.ts`) — from `GET
  /savings-goals/timeline?months=N` (`0` = all; `total_months` says whether
  "All" adds anything). Collapsed by default and fetched only when opened.
  Monthly bars are each goal's `change` that month; Cumulative bars are its
  month-end `balance`; free cash is stacked on top. Positives stack up from
  zero and negatives down (`STACK_OFFSET = "sign"`). The legend is
  clickable (click hides a series, double-click isolates one, the y-axis
  refits), series colour is keyed by goal **id**, and only the outer segment
  of a stack is rounded (`charts/stackedBarShape.tsx`).
- **Monthly budget** (`SavingsGoalsBudgetSection.tsx`) — what moved into and
  out of each goal that month (`added` / `income` / `spent`), from
  `get_month`. It rides on `GET /budget/analysis/{year}/{month}` as the
  `savings_goals` key, **not** its own request (an extra per-month call
  pushed the budget page's refresh past the `budget-create-rule` e2e
  deadline). `GET /savings-goals/month/{y}/{m}` exists for direct callers.

The ledger is computed per request (`_ledger_cache`, dropped by every write
through `_invalidate`) and nothing derived is persisted, so there is no
"ensure"/"rebuild" step and no read path ever writes.

## This year's savings: measured, not earmarked

The top of the dashboard card (`YearlySavingsSection.tsx`) answers a
different question from the goals: how much did each year *save*, against a
target set for it? `yearly.py` (`YearlySavingsMixin`) computes it straight
from the transaction context — never from what the goals hold — so putting
money into a goal or taking it out never changes it; only what a goal claims
as its own money does.

A month saved its income minus its spending:

- `surplus` (which already took investing out) **plus `invested`** — the net
  money moved into investments that no goal link claims. Investing is saving;
  a withdrawal is neutral until it is spent, and a spent withdrawal is
  spending, so a month or a whole year can be negative (red text, empty bar).
  Gains and losses on investments never appear.
- Loans as the rest of the app counts them: a receipt is income, a repayment
  spending.
- **A goal with a saved-into rule:** its income is the goal's money, not the
  year's savings, and the bills it pays with that income are not the year's
  spending. Only the part of its bills beyond the income received so far
  (cumulative, per goal) is spending, counted in the month it crosses.
- **A goal without one:** its utilizations are spending in the month they
  happen — the money was saved before and is being spent now.

Targets are one per calendar year (`yearly_savings_targets`, `year` primary
key; `PUT /savings-goals/yearly/{year}/target` with `null` clears it, a
non-positive amount is a 400). `pace` exists only for the current year with a
target: `expected_by_today = target × elapsed days / days in year`, `ahead_by`
is negative when behind, and `needed_per_month` spreads what is left over the
months left **including the current one**.

The response carries every year from the first month on record to today (plus
any year with a target), each with its months (the card names the last three years; it no longer
draws this year's months as bars). Its query key
(`qk.savingsGoals.yearly()`) sits under the savings-goals prefix, so every
goal write refreshes it.

## Gotchas

- **Compare against a target with `ROUNDING_EPSILON`, never bare `>=`.** A
  goal's totals are summed from many entries and transactions, so one that
  filled exactly can land a hair under its target through float error and
  render "100%, 0 to go" while `is_achieved` is false.
- **Demo Mode ships five goals** (`create_savings_goals` in
  `scripts/generate_demo_data.py`), each with monthly entries, the wedding
  fund paying two linked bank transfers. Entry `date`s are real dates and
  `_shift_dates` moves them by the day offset; `start_month` /
  `closed_month` move by whole months.
- `SavingsGoal.status` / `is_achieved` / `is_closed` arrive from SQLite as
  0/1 integers. Guard them with `!!` in JSX — `{0 && <Check/>}` renders a
  literal "0" beside the goal name (there is an e2e pinning this).
- The frozen demo snapshot is schema-synced by `demo_setup.py`, which only ever
  *adds* columns. A retired `NOT NULL` column left behind breaks every ORM
  insert into that table, so `RETIRED_COLUMNS` drops it — that is why
  `savings_goals.current_amount`, `opening_balance` and `monthly_cap` are
  listed there.
- **Migration `31ce8f3f673d` carried the old ledger over as entries**: each
  (goal, month) allocation became a `migrated` entry dated the 1st, an
  opening balance an entry at the start month. It reads the persisted
  `savings_goal_allocations`, so a goal's history is exactly what the old
  card last stored.
