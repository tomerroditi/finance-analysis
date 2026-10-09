---
paths:
  - "backend/services/savings_goals/**/*.py"
  - "backend/routes/savings_goals.py"
  - "backend/models/savings_goal.py"
  - "frontend/src/components/dashboard/GoalsSection.tsx"
  - "frontend/src/components/budget/SavingsGoalsBudgetSection.tsx"
  - "frontend/src/components/budget/BudgetGoalLink.tsx"
  - "frontend/src/components/dashboard/GoalAutoLinkField.tsx"
---
# Savings Goals — the surplus waterfall

How the `backend/services/savings_goals/` package turns each month's leftover
money into goal progress. `SavingsGoalService` (`core.py`) assembles mixins:
`inputs` (goal order, the transaction context, the pre-goal pool),
`engine` (`_simulate`, `_persist`, `ensure_allocations`, `rebuild`), `goals`
(CRUD + transaction links) and `read_models` (enriched goals, month view,
free cash, timeline); `common` holds the pure month helpers and `ROUNDING_EPSILON`.
Read this before touching the service, the `savings-goals` routes,
`GoalsSection.tsx`, or the goals block on the monthly budget view.

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
           + incoming contributions past their goal's target (spill-over)
free_cash += surplus                             (the pool moves with the month)
pool       = max(0, surplus)
pool      -= frozen allocations of closed goals  (already spoken for)
pool      -= outgoing contributions              (consume before the waterfall;
                                                  incoming ones credit the goal, spill the rest)
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
  un-funded once that pool is empty, and what no goal can give back leaves
  the pool negative.
- **`monthly_cap` is what stops a big goal starving the rest.** Uncapped, a
  priority-1 goal absorbs everything until it fills.
- **`start_month` gates participation**: nothing is allocated to a goal
  before it. It defaults to the creation month. Free cash that built up
  before a goal started is not lost to it, though — the waterfall hands out
  the whole pool, so the goal picks that money up in its start month.
- **A closed goal replays its history up to the month it closed**
  (`closed_at` / `locked` in `_simulate`): its stored rows stand, and the
  income, bills and borrowing derived every pass still run, until its closing
  month; only then is it frozen. Frozen from its first month, it skipped the
  borrowing that had paid its bills, so every read after it auto-closed
  rewrote its history (a wedding fund read 213K against a 199K target).
- **A target date ends a goal's turn** (`open_for` in `_simulate`): it takes
  new money — waterfall surplus, or a deposit no goal's cash covers — only up
  to its target month. Past it, it keeps what it holds and can still invest
  that cash, and the surplus moves on to the goals below. Without the end, a
  "Yearly savings 2024" goal at the top of the order took every surplus of
  2025 and 2026, starving every goal below it.

## The free-cash pool

The counterweight to the goals is `free_cash`: the tracked money no goal has
earmarked. It exists so an overspent month has somewhere to land before the
engine starts taking money back out of the goals.

- **It opens at the spendable money that existed when the first goal started** —
  bank + cash *prior wealth* (`_opening_free_cash`, investment prior wealth
  deliberately excluded: money in an investment is not free cash), walked
  forward through every month of realized surplus that predates the walk.
  Anchoring on prior wealth alone would ignore all the history the goals never
  saw.
- **An opening balance leaves the pool in its own goal's start month** (a
  future start: the current month), in full — the pool may go negative for
  it. Floored at zero, a balance bigger than the pool earmarked money that
  was never there, and `liquid` read above the bank. They used to all leave
  when the *earliest* goal started, so a later goal's opening balance emptied
  the pool months early: the deficit in between clawed back goals that had
  done nothing, and claiming a goal's earlier free cash moved the figure it
  had just claimed. `test_an_opening_balance_leaves_the_pool_when_its_goal_starts`
  and `test_claiming_does_not_move_the_figure_it_claimed` pin it.
- **That pre-goal history is not floored either**, just like the walk. A
  floor anywhere made the result depend on where it sat: summing and flooring
  once put it at the earliest goal's start, so deleting that goal moved it (a
  120K goal once released only ~34K). Deleting a goal must hand back exactly
  what it held and leave `liquid` unchanged;
  `test_deleting_the_earliest_goal_releases_its_earmark` pins that.
- **`liquid` must equal the tracked bank + cash balance, to the shekel.** The
  pool is prior wealth walked forward through the realized surplus, so both
  halves of every balanced pair must be in it. **Manual investments are such
  a pair**: their deposits are tracked transactions (they leave the pool when
  they happen, and an investment goal counts them), and their investment
  prior wealth — `-(sum of those deposits)` — is the money that paid for them
  outside any tracked account. `_opening_free_cash` therefore adds investment
  prior wealth (open and closed investments, as the net-worth chart does) to
  bank and cash. Counting the deposits without it took a user's 151K of
  manual deposits out of free cash with nothing to pay for them, and the
  pre-goal floor hid most of it; the data was not duplicated, the engine read
  half of the pair. `test_savings_goal_invariants.py` checks `liquid == bank`
  on random households after every edit.
- **It moves with the whole month, not just the positive part.** The pool is
  credited with the surplus itself and debited for every shekel a goal takes
  out of it. What the goals do not claim simply stays in the pool.
- **It goes negative, and shows it.** Once the pool and the clawable goals are
  exhausted, what is left of an overspend was paid with money no goal can give
  back (an income goal's own income, money already invested) or money this
  model does not track (an overdraft, an untagged account). Either way it was
  spent, so the pool carries the whole hole and the card shows it in red. It
  used to floor at `-income_held()` and, before that, at zero; both hid real
  overspending — a 22.5K January of wedding bills read as an exact 0.
- **A hole is repaid before any goal is funded.** The waterfall distributes
  `max(0, min(surplus, free_cash))`, so a later surplus first refills the pool
  and only the rest reaches the goals.
- **A carried hole never claws back again.** Each month's clawback reaches the
  goals only for a fall below `min(0, month_start + max(0, surplus))` — the
  hole it inherited, less what its surplus repaid. Measured against zero, a
  hole carried from an earlier month took goal money back every month after;
  measured against the bare month start, an overspend after the surplus had
  repaid the hole and funded a goal never reached that goal.
- **It is spendable cash, not a bank statement.** Investment transfers reduce it
  for the same reason they reduce the surplus, so it will sit below the raw
  bank + cash balance for anyone who invests.
- **The waterfall hands out the whole pool, not just the month's new
  surplus** (`pool = max(0, free_cash)`). Free cash exists to fill goals: it
  is left over only once every goal that can still take money is full,
  capped for the month, or past its target month. Distributing only each
  month's new surplus left 100K idle on real data while goals sat short —
  money already in the accounts when a goal started, and bills a wedding fund
  borrowed for and its gifts repaid, never reached any goal. The trade-off:
  with no idle pool to cushion it, a deficit month reaches the goals (lowest
  priority first) straight away.
- **No free-cash claim.** The row's wallet action and the editor's "use the
  free cash before …" shortcut are gone — the waterfall already gives a goal
  the free cash waiting when it starts. `GET /savings-goals/free-cash/before`
  (`get_free_cash_before`) stays on the API. "Already saved" (the opening
  balance) stays, for money held outside the tracked accounts.
- **Moving an opening balance restates history.** Stored months keep their
  rows, so a new opening balance replayed against old ones leaves the pool
  short — the next deficit month then claws the difference back out of
  whichever goal has no row there, which is the wrong goal. `update` restates
  it (see "Editing a goal restates its history" below), and the editor says so
  before the user saves.
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
  out on its own. `clawed_back` on the API payload sums those rows. The
  dashboard card deliberately does **not** show that lifetime total: once
  later surplus refills the goal it is history, not a shortfall, and a
  standing amber "taken back" line on a full goal read as something being
  wrong (an investment transfer counts as a deficit too, so the old
  "overspending" wording was often false as well). Clawbacks surface where a
  month is in view instead — the free-cash note for the current month, the
  budget month's banner, and negative bars in the history panel.
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

## Investment goals: filled by transfers, not by surplus

A goal has a `kind` (`savings_goals.kind`; `NULL` — a row
older than the column, or a demo DB synced by `sync_missing_columns` — reads
as `cash`, via `common.is_investment_goal`). A **cash** goal is everything
else in this file. An **investment** goal answers "have I invested X?":

- **Progress is the net amount moved into investments.** Its
  `contribution_category` is always `INVESTMENTS_CATEGORY` — the service sets
  it on create and ignores any change, since every investment transfer lives
  in that one category — and its optional `contribution_tags` narrow it to
  some holdings (e.g. Pakam); none means every investment. `_goal_by_transaction` maps them as `LINK_INVESTED` (never stored),
  **signed** and gated on `start_month` — deposits add, withdrawals take back,
  earlier transfers stay ordinary. `_compute_context` reports them in
  `invested`, out of the surplus.
- **It never takes part in the waterfall or its clawback**, and never
  auto-closes. `funded` is only its transfers (the plan records them in
  `contributed`); the row's `this_month_allocation` is the month's net
  transfers, shown as "invested" / "withdrawn".
- **Investing is progress, not overspending.** A transfer to a plain
  Investments category is a deficit that can claw back the cash goals — a
  75K month into a savings deposit used to take money back out of a trip
  fund. An investment goal's transfers leave the free-cash pool (the money is
  no longer liquid) *after* that month's clawback, floored at zero, so they
  can never reach another goal. A withdrawal hands the money back. The flip
  side: a transfer the pool could not cover is treated as untracked money,
  so `liquid` can sit above the bank for that amount.
- **It is not cash.** `get_free_cash` leaves it out of `earmarked` and
  `liquid`.
- **It can name the income that pays for it** (`funding_category` /
  `funding_tags`, "Paid from income" in the editor; investment goals only).
  `_goal_by_transaction` maps that income as `LINK_FUNDING` (never stored,
  from the goal's start month), `_compute_context` reports it in `funding`,
  out of the surplus, and `_simulate` keeps it in `to_invest`: each deposit
  is paid from it first and only the rest leaves free cash; a withdrawal
  still goes back to free cash. What is not yet invested is cash the goal
  holds — the payload's `to_invest` ("… ready to invest"), counted in
  `earmarked` and in how far the pool may go negative.
- **Every investment goal holds cash and takes its waterfall turn.** Its
  progress is what it holds — income, waterfall surplus and new money
  invested — invested or not. Investing only moves its cash (`plan.invested`,
  which the card's "invested this month" reads). A plain investment goal used
  to be filled only by transfers and skipped the waterfall, so a January
  withdrawal left "Yearly savings" at −40K beside 300K of free cash.
- **Two investment goals can match one transfer** (both counting every
  Investments transfer, say). `_goal_by_transaction` no longer settles it —
  it returns each transfer's *group* of matching goals, highest first, and
  `invested` is keyed by group. `_split_transfer` splits each month's net per
  group: a deposit first draws on the cash the goals hold (highest first);
  the rest is new progress for the highest goal still short of its target
  that has no income of its own, paid from free cash, or an ordinary transfer
  when there is none. A withdrawal goes back into the cash of the goals that
  invested, never past what each invested; the rest returns to free cash. So
  no investment goal goes negative. Rules used
  to be applied in waterfall order with the last writer winning, so the
  *lowest* goal took every shared transfer from its start month on: a
  "Yearly savings" goal started in January swallowed the deposits made out
  of a June wedding gift, and the "Marriage kickstart" goal the gift was for
  sat on 200K "ready to invest" that had already been invested. Saved-into
  rules that overlap now go to the higher goal too, as documented.
- **A goal can switch kind** (`update(kind=...)` → `_change_kind`, the
  editor's type choice is shown when editing too). What one kind is filled by
  means nothing to the other, so the switch clears it — to investment: the
  opening balance, cap, spending rule, saved-into rule and single-transaction
  links, with the rule set to Investments; to cash: the investment and
  funding rules — then applies the fields sent with it and restates history
  from the earlier of the old and new start months. A closed goal must be
  reopened first. The editor warns before saving and blanks the rules of the
  kind it leaves (restoring them if switched back).
- **One income feeds one goal.** A saved-into rule and a funding rule both
  claim income, so `_validate_income_claims` refuses a second claim on the
  same category (overlapping tags, or either side covering every tag), and a
  funding rule on a cash goal.
- **Cash-goal settings are refused** (`_validate_investment_fields`,
  `_reject_investment_goal`): it takes no
  `opening_balance`, `monthly_cap`, spending rule or single linked
  transaction. The editor
  offers only name, target, start, date and "Only these investments" (a
  tags-only picker, `InvestmentTagsField`).
- **Creating, rescoping or deleting one restates history from its start
  month** (`_restate_for_transfers` → `rebuild`). Which transfers it owns
  decides, in every month they touch, whether they are progress or a deficit
  that clawed back the cash goals; applying that only forward would leave
  every old clawback in place. Pinned by
  `test_creating_and_deleting_it_restate_the_past`.

## Goals with income of their own: exactly that income, surplus for the gap

A cash goal with a `contribution_category` (a "saved into" rule — the wedding
fund fed by `Other Income / Wedding`), and an investment goal with a funding
income, are **filled by that income first** and still **take their waterfall
turn** for the rest.

- **Surplus fills only what the income will never cover.** `surplus_room`
  is the target less every shekel of the goal's own income in the history
  (known to date), and caps its `fill`. A goal whose income meets its target
  takes no free cash at all, even in the months before the income lands —
  bills there are fronted and repaid. The user's words: Marriage kickstart
  "takes from free cash instead of the connected income, while the connected
  income has the exact same amount it needs". The release below is now only
  a safety net (income that grows past what the history showed).
- **Surplus it does take is ordinary waterfall money** (`fill` in
  `_simulate`, written as ordinary ledger rows). Income is measured against the target *ignoring*
  that surplus, so it is always kept; once goal-held money passes the target,
  `give_back_fill` returns the surplus the income made unnecessary to free
  cash as a negative row in the income's month. A goal whose income covers
  its target therefore ends holding the income alone; one whose income falls
  short is topped up from free cash in priority order. The user asked for
  this explicitly ("free cash should always fill the goals in a waterfall
  manner"): a 300K kickstart goal funded by 300K of gifts showed 192K while
  it ignored the waterfall.
- **A deficit reclaims only that surplus, never the income.** The clawback
  caps an income goal's give-back at its `fill`. An earlier waterfall version
  without that cap clawed a 300K goal's own gifts back and refilled it with
  surplus, so it showed 255K made of the wrong money. Its other failure —
  salary parked in the goal for a year while it waited for the gifts — is
  now the intended behaviour: that is the goal's place in the waterfall, and
  the gifts hand it back when they land.
- **A closed goal's later income is ordinary money.** Income its rule
  matches after it closed joins the month's surplus (a funded investment
  goal's too); it used to be kept without limit, so a closed 3K goal held
  34K. Its saved-into rule matches only from its start month, like every
  rule — income before it was claimed, never walked, and vanished.
- **Income that repays the goal's bills is kept even past target.** When the
  income lands on a goal already at target that borrowed for its bills, the
  repaying part is its income spent on them; spilled as well, the same money
  reached free cash twice and the goal read a negative `available`.
- **Surplus that reaches a goal still owing for a bill repays that debt
  first** (`repay_bridge`, recorded in `plan.released`), exactly as its
  income would; a replayed positive row does the same, so a rebuild and a
  replay agree.
- **History replay: a goal with rows elsewhere is no newcomer.** In a
  non-recomputed month only a goal with no stored rows at all may take what
  the month left unallocated. A net row hides a take that a same-month
  deficit gave back, so the old "no row this month" test let a lower goal
  grab that surplus on every replay (a wedding fund gained 14.6K per read).
- **A bill that lands before the income is paid with borrowed free cash**
  (`plan.fronted`, tracked in `bridge`): the goal pays it in full and owes the
  gap. **Income repays the bridge first** (`plan.released`, credited back to
  free cash); what is still owed when no more income comes — bills beyond the
  gifts — stays owed, and a goal that owes never auto-closes.
- Income past the target still spills into the month's surplus.
- **Its progress is what it received, never what it owes.** `funded` is
  opening + surplus + income; free cash borrowed for bills and not yet repaid
  is reported as `owed` ("… paid from free cash" on the card) and only adds
  to what it could spend (`available = funded + owed - utilized`). Counting
  the debt as funding showed a wedding at 100% on money it never got, and
  its bars (which are its income) never added up to the card.
- Fronted and released amounts are derived every pass, like contributions,
  never ledger rows. `funded = opening + allocated + contributed + fronted -
  released` and the payload reports `fronted` / `released`. The month view
  and timeline report the net apart as `bridged`, **outside** each goal's
  `total`: a goal's bar is what it received (surplus and income), so a gift
  month that repaid earlier bills still reads as the whole gift. Netted in, a
  164K gift month showed as 85K and read as the goal ignoring its income.
- **Creating, rescoping or deleting the rule restates history** from the
  goal's start month (`_restate_for_transfers`, shared with investment
  goals).

Pinned by `TestRuleFundedGoals`. Migrations `1f504bcccd13` and `6950d212e44e`
clear the open goals' ledger so existing data is recomputed under these rules.

### A goal pays only with what it holds

Any goal's spending is capped at `funded - utilized`; `plan.spent` is what it
actually paid and is what `utilized` reports. The rest of the bill came out
of free cash — it is debited there (an income-funded goal borrows it, above;
any other goal simply leaves it with free cash). Before this, a bill bigger than
the goal left `available` negative and never touched free cash, so the pool
read high by the overshoot.

## Investment backing was removed

Goals could once earmark a holding (`savings_goal_investments`, valued live
off the investment). It was dropped once investment goals existed: an
investment is just a category and tag, so money moved into one is tracked
the same way any other transfer is, and a goal about it is an investment
goal. Migration `b9a0f25d4d28` drops the table. Don't reintroduce a second
way to count the same holding toward a goal.

## Every shekel is counted once

Transactions linked to a goal are **pulled out of the surplus calculation**
(`_compute_context`) and reintroduced explicitly:

| link | effect |
|---|---|
| `contribution`, outgoing (a transfer out to savings) | credits the goal **and** consumes the pool before the waterfall |
| `contribution`, incoming (a gift, sale proceeds) | credits the goal up to what it still needs; the rest spills into the month's surplus |
| `utilization` | reduces the goal's `available`, leaves the pool alone |

A utilization does **not** reduce `target_amount` — buying the thing you saved
for is money *used*, not a smaller goal. And it must not reduce that month's
pool either: the money was set aside in an earlier month, so charging it again
would double-count it.

Leaving a linked transaction inside the surplus *and* deducting the
contribution from the pool is the bug this design exists to prevent; it nets to
the same total by deducting the same shekel twice.

The same trap runs the other way for **incoming** money. A gift linked to a
goal is already out of the surplus; charging it to the pool as well took it
out a second time, sent the pool negative by the size of the gift, and the
clawback then pulled the gift straight back out of the goal it had just
funded (a 100K wedding gift showed up as ~97K "taken back to cover
overspending"). `_compute_context` therefore reports `drawn` — the outgoing
part of `direct` — and only that is debited from the pool.
`test_incoming_contribution_is_new_money_not_a_draw_on_the_pool` pins it.

**Incoming money past the target spills over.** A goal keeps only what it
still needs of an incoming contribution (`target - funded - backed` at that
point in the walk); the excess joins the month's surplus and flows down the
waterfall like any other income — the same "a goal never takes more than it
needs" rule the waterfall applies. Wedding gifts linked to a 200K goal that
come to 490K fill the goal and hand the rest on. Outgoing contributions are
never capped: that money deliberately left the account. Because what a goal
kept depends on how full it was, only the simulation knows it: the plan
carries it as `contributed` (and the spill-inclusive `surplus`), and the read
models report those rather than the raw linked transactions. A closed goal's
contributions stay as they were — frozen. Pinned by
`test_incoming_contribution_past_the_target_spills_down_the_waterfall`.

A goal may also name a `contribution_category` (+ optional semicolon-separated
`contribution_tags`, the budget-rule convention) to accrue matching
transactions automatically. An explicit per-transaction link always wins over
the category rule, so one correction beats the broad match.

### Paying for a budget out of a goal

The mirror image of `contribution_category`: a goal may name a
`utilization_category` (+ optional semicolon-separated `utilization_tags`;
`NULL` = every tag) whose spending is **utilized from the goal**
automatically — the purchases already on record and every one scraped later —
so nobody links a budget one transaction at a time. Three ways to set it:

- **Project tab** — `BudgetGoalLink` in the command bar links the project's
  category (all tags).
- **Yearly tab** — the target icon on an envelope row links its category and
  tags.
- **Goal editor** (`GoalAutoLinkField`) — "Spent from this goal" /
  "Saved into this goal" set the utilization and contribution rules directly.

The budget buttons go through `PUT /savings-goals/{id}/spending-link`
(`{category, tags}`, `category: null` clears), which also **releases any other
goal holding the identical rule** in the same commit; the editor writes the
columns through the ordinary goal update. Rules:

- **Signed, not `abs`.** Rule rows keep their direction (`_GoalLink`'s
  `signed` flag), so a refund nets against the purchases it repays. Explicit
  links still count by magnitude, as they always have.
- **Only from the goal's `start_month`.** Spending that predates the goal was
  never paid out of it and stays an ordinary expense of its month. Counting it
  would also pull it out of pre-goal surplus that no goal ever walks, inflating
  the opening free-cash pool.
- **Card purchases count.** Budgets are mostly paid by card, and card rows
  never enter the surplus (the bank-side bill does). A card row mapped to a
  utilization — by a rule or an explicit link — is utilized from the goal
  **and** its amount is handed back to its month's surplus, because the bill
  that paid for it is already in there. Without the hand-back the same shekel
  leaves both the pool and the goal. (Before this, an explicit link on a card
  row was silently ignored.)
- **Overlaps resolve by waterfall order** — when two goals' utilization rules
  match one row, the higher-priority goal takes it.
- **Precedence:** contribution rule < utilization rule < explicit link.
- **A rule is a category/tag match, not a budget reference.** Deleting the
  project or envelope leaves the goal's rule in place (it still names real
  transactions); a rule naming an unknown category simply matches nothing.
- **History stands.** Linking changes past months' surplus, but their stored
  allocations do not move; the spend simply comes out of the goal instead of
  out of free cash, so `liquid` is unchanged. A `rebuild` restates them if the
  user wants the freed surplus redistributed.

## History is never silently restated

Allocations persist per `(goal, month)` in `savings_goal_allocations`.

- `ensure_allocations()` **always recomputes the current month**, which is
  provisional until it ends, and every month after the ledger's last month
  with rows (`horizon` in `_simulate`) — a month nobody opened the app in.
- **A month on record replays its rows and nothing else**: no waterfall take,
  no clawback. There is no "newcomer" backfill any more: every create, edit,
  link and deletion restates history, so a goal never arrives in a month on
  record. The backfill let a goal with no row take what a net row (a take a
  same-month deficit gave back) made look unclaimed, and every read then
  wrote a new row on top of the last — rebuild and read disagreed.
- **Links restate too.** `link_transaction` and `unlink_transaction` rebuild
  the whole history (a link can move a transaction between goals), and
  `set_spending_link` restates from its goal's start month. Explicit links,
  like every rule, count only from the goal's start month: a row linked
  before it left the surplus and was never paid by anything.
- **A new order needs a fresh transaction context.** When two goals' rules
  match one row, the higher goal takes it, so `rebuild(order=...)` drops the
  cached context before and after; reused, a reorder restated history under
  the old order's matching.
- **Editing a goal restates its history.** Every goal takes its waterfall
  turn, so a change to anything in `_ALLOCATION_FIELDS` (start month, target,
  cap, opening balance, saved-into / spending / investment / funding rules)
  makes `update` rebuild from the **earlier of the old and new start month** —
  moving a start later must clear the months it no longer covers. `create`
  and `delete` always restate from the goal's start month too. Only an edit to
  the transfer rules of an income or investment goal used to restate; moving
  a cash goal's start date, or changing any goal's target, kept every past
  month as it was. The client no longer calls `rebuild` after an edit — the
  update already did.
- **Reordering restates everything.** `reorder` sets the
  priorities and runs a full `rebuild` in the same call. It used to apply
  forward only, with a separate previewed "Redistribute" to restate history
  — which left the list saying one order while every past month was still
  allocated under the old one, until the user found the button. Closed goals
  keep their frozen rows, as in any rebuild. `dry_run=True` stays on the
  endpoint, but no screen previews any more.
- **A rebuild computes first and writes last, in one transaction.** The new
  order (reorder passes it as `rebuild(order=...)`, simulated via
  `_order_override` without touching the stored priorities), the deletion of
  the restated range and every replacement row commit together inside
  `SavingsGoalRepository.atomic()`. Committed one by one, a request running
  alongside — another tab's reorder, or any read whose `ensure_allocations`
  fills in missing months — could see the history deleted but not yet
  rewritten and refill it under the old order, double-counting money. Two
  rules keep the block safe: **nothing but writes runs inside it** (several
  repositories read through `pd.read_sql(..., self.db.bind)`, their own
  connection, which in the in-memory test engine is the *same* SQLite
  connection — its rollback-on-close silently undid an open transaction), and
  **a block that wrote nothing does not commit**, since every commit discards
  the `data_cache` generation and `_persist` opens a block on every read.
  `test_a_reorder_that_fails_midway_changes_nothing` pins the all-or-nothing
  half.
- **The card answers the click before the server does.** The reorder
  mutation patches the list's order in `onMutate`, and its figures pulse
  with a "Recalculating…" status until the rebuilt ledger arrives. Reorders
  share one mutation `scope`, so rapid clicks reach the server one at a
  time, and only the last one in the queue writes its answer. The list query
  is **disabled while any reorder is pending**: a refetch in between (an
  earlier reorder's invalidation, or the app-wide sweep) returns an order
  the user has already moved past and snaps the rows back. A disabled query
  keeps its data and ignores invalidation, then refetches once re-enabled.

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
  free-cash pool on a dashed row below the goals (`GET
  /savings-goals/free-cash`, its own query key). The waterfall **scrolls in
  place** past about 26rem of rows, so a household with a dozen goals does not
  push the pool row and the history panel off the card — but only once the cap
  hides about a row's worth (`useScrollCap`), because a list that scrolls by a
  hair swallows the drag meant for the page (`frontend_pitfalls.md` →
  "Capped Scroll Regions"). A goal's **name owns its
  own line** in the row: sharing one with the funded/target pair and five
  action buttons left it about eight characters wide on a phone, so the row
  named nothing at all.
- **Dashboard history** (`AllocationHistory` in the same file) — the same
  ledger read the other way round, from `GET /savings-goals/timeline?months=N`
  (`0` = all time; `total_months` is what tells the UI whether "All" would
  add anything). It is **collapsed by default**: the standings above answer
  "where is each goal now", which is what the card is opened for, and the
  ledger behind them is a second question that costs a chart and a request.
  The timeline query is `enabled` on the panel being open, so a card nobody
  expands never fetches a window.

  Stacked bars carry each month's per-goal funding **with the free-cash pool
  stacked on top**; a negative segment is a clawback. Positives stack up from zero and negatives
  down from it (`STACK_OFFSET = "sign"` in `charts/stackedBarShape.tsx`) —
  Recharts' default piles a negative segment onto the positive column and
  draws it over the bars. The pool is a standing
  balance and the allocations are monthly flows, so on a household with real
  savings the pool towers over them — which is why **the legend is
  clickable**: a click hides a series (the pool included) and the y-axis
  refits to what is left, and a double-click narrows to one series, with a
  second double-click on that same one bringing the rest back. Isolation is
  tracked explicitly rather than inferred from "everything else is hidden", so
  a double-click never undoes a selection the reader built click by click.
  Hidden series dim in the legend rather than disappearing from it, so the way
  back is where the way out was.

  Series colour is keyed by goal **id**, not by priority, so reordering the
  waterfall never repaints the chart. Only the outer segment of a month's
  stack is rounded (`charts/stackedBarShape.tsx`, shared with the retirement
  income chart) — rounding every segment renders a column as a string of
  beads — and the rounding follows the *visible* stack, as does the zero
  line.
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

- **Compare against a target with `ROUNDING_EPSILON`, never bare `>=`.**
  `funded` is accumulated by summing dozens of stored rows, so a goal that
  filled exactly can land a hair under its target through float error — it
  then renders "100%, 0 to go" while `is_achieved` is false, and never
  auto-closes. Both the enrichment and the auto-close check absorb half an
  agora; there is a unit test pinning it.
- **Demo Mode ships three goals** (`create_savings_goals` in
  `scripts/generate_demo_data.py`) covering achieved, investment-goal and
  utilized states. Allocations are deliberately *not* seeded — the engine
  derives them on first read, after `_shift_dates` has re-anchored
  `start_month` / `target_date`. A spec that asserts absolute waterfall
  positions must clear those goals first.
- `SavingsGoal.status` / `is_achieved` / `is_closed` arrive from SQLite as
  0/1 integers. Guard them with `!!` in JSX — `{0 && <Check/>}` renders a
  literal "0" beside the goal name (there is an e2e pinning this).
- The frozen demo snapshot is schema-synced by `demo_setup.py`, which only ever
  *adds* columns. A retired `NOT NULL` column left behind breaks every ORM
  insert into that table, so `RETIRED_COLUMNS` drops it — that is why
  `savings_goals.current_amount` is listed there.
