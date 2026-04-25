# Next Features — Brainstorm

A prioritized backlog of major features and improvements. Each entry has a
"why" (the user pain it removes) and a rough sense of cost. None of these are
committed; this is the running idea board.

## Tier 1 — High value, manageable scope

### 1. Forecasting / cash-flow projection
**Why:** The README and original goals call for a forecast feature, but it's
unimplemented. Users see history but not "if I keep spending like this, when
do I run out?" or "what's my projected savings rate over the next 12 months?"

**Shape:** A new `ForecastService` that runs simple linear / EMA projections
on monthly income & expenses by category, plus what-if sliders ("if I cut
restaurants by 30%…"). Render as an extension of the `EarlyRetirement` page
or a new `Forecast` page with a stacked area chart.

**Cost:** Medium. The data is already there; the work is the projection
math + UI + tests.

### 2. CSV / OFX import for non-Israeli accounts
**Why:** The whole stack assumes Israeli scrapers. Users with foreign
accounts (USD brokerage, EU bank) have no way in. A `manual_investments`
row works but is per-transaction tedious.

**Shape:** New `ImportService` that accepts CSV/OFX, lets the user map
columns to our schema (date / amount / description / etc.), runs through
the existing tagging-rules engine, and writes to either
`bank_transactions` or `manual_investment_transactions`. UI is a wizard
modal with column-mapping preview.

**Cost:** Medium. Most parts already exist; mainly UI work + a new
parser layer.

### 3. PWA / offline-first mobile shell
**Why:** Mobile UX has been heavily polished (see
`.claude/rules/frontend_responsive.md`), but every navigation re-fetches
from the server and the app dies offline. Wrapping in a service worker
gives "open the app on the bus, see last-week's numbers" for free.

**Shape:** Add `vite-plugin-pwa`, cache the static build, persist React
Query cache to IndexedDB, mark which API calls are safe to read from cache
(transactions: yes; scraping: no).

**Cost:** Small-medium. Mostly config + a thin abstraction over query
cache.

### 4. Push / in-app notifications for budget alerts
**Why:** Today, the user has to open the dashboard to notice they blew
through 80% of the food budget. A simple "you're 90% through your
restaurants budget for the month" notification turns insight into action.

**Shape:** Backend cron-equivalent (we don't have a job runner — start
with on-app-load checks first), frontend Notifications API with permission
prompt, opt-in per budget rule.

**Cost:** Small (in-app), Medium (true push — needs FCM or similar).

## Tier 2 — High value, larger scope

### 5. Multi-user / household support
**Why:** The system is single-user. A couple sharing finances has to either
share a login, run two instances, or merge data manually. Sub-accounts
inside one DB would let two people share a household view while keeping
private accounts private.

**Shape:** Add `users` and `account_owners` tables; tag every transaction
with an owner; introduce a "household view" that aggregates and an
"individual view" that filters. Auth becomes real (today there is none).

**Cost:** Large. Touches every repo, every analytics method, every page.
Auth alone is a multi-week project.

### 6. PDF / shareable monthly report
**Why:** Users sometimes want to send a household budget summary to a
partner / accountant / parents without sharing the live app. A clean
one-pager PDF — KPIs + Sankey + monthly bar chart — would close the loop.

**Shape:** Server-side render via WeasyPrint or playwright-pdf. New
`/api/reports/monthly?year=Y&month=M` endpoint returns a PDF, with a
"Share monthly report" button on the dashboard.

**Cost:** Medium. The data is one endpoint away; layout is the work.

### 7. Investment performance comparison vs. benchmarks
**Why:** Users see absolute ROI on each investment but can't tell if they're
beating S&P 500 / TA-125 / a savings account.

**Shape:** Pull a benchmark series (TASE has free EOD CSV; Yahoo Finance
unofficial API) into a new `benchmarks` table; let the user attach a
benchmark to each investment; the existing balance-over-time chart gets a
dotted overlay line.

**Cost:** Medium. The benchmark fetch + storage is the new piece; chart
work is small.

## Tier 3 — Quality of life

### 8. Categories drag-and-drop reorder is mouse-only
The categories page supports drag-and-drop, but on touch it doesn't trigger.
A simple "Move up / Move down" button row in mobile context-actions fixes it.

### 9. Transaction-level "expected to repeat" flag
For recurring rent, salary, subscriptions — let the user mark them, and
forecasting / budget rules can use the flag to project forward
deterministically rather than statistically.

### 10. Inline category create-on-the-fly — DONE
`SelectDropdown.onCreateNew` is now wired across the remaining
category/tag forms:

- `RuleManager` (auto-tagging quick-rule modal) — category + tag
- `Liabilities` new-debt form — Liabilities-scoped tag (chained into
  `handleTagChange` so receipt detection still fires after create)
- `Investments` new-investment form — Investments-scoped tag (the
  category field is intentionally pinned to `Investments`, so only the
  tag dropdown takes inline create)

Already had it before this pass: `SplitTransactionModal`,
`BulkActionsBar`, `TransactionFormModal`, `TransactionEditorModal`,
`BudgetRuleModal`, `RuleEditorModal`, `RecentTransactionsSection`.

Deferred: `ProjectModal` — its category dropdown is fed by a derived
"categories not yet used as a project" backend list, so wiring inline
create there needs coordinated cache invalidation and is a different
shape than the others.

### 11. Dark / light theme toggle
Today the UI is dark-only via CSS custom properties. Adding a `light`
variable set and a Zustand-backed toggle is a one-week effort and a popular
ask.

### 12. Audit log
Every mutation (transaction edit, category rename, snapshot delete) appended
to an `audit_log` table with timestamp, before/after JSON. Supports "what
did I do last Tuesday?" + recovery from accidental edits.

## Engineering debt to clear alongside features

These aren't features but unblock the features above:

- **Job runner.** Notifications, scheduled scrapes, snapshot jobs all need
  one. APScheduler or a tiny in-process loop will do.
- **Real auth.** Currently relies on "single user on localhost". Multi-user
  needs at minimum sessions + password hashing.
- **Migration coverage.** Only 2 Alembic migrations exist; the rest of the
  schema lives in the lifespan handler (`backend/main.py`) doing manual
  `ALTER TABLE` on startup. Move those into migrations so a fresh DB and an
  upgraded DB end up bit-identical.
- **Frontend bundle splitting.** Plotly is huge; lazy-load it from the
  dashboard route only.
