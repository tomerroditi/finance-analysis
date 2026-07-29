# Retirement / FIRE Calculations

How `backend/services/retirement_service.py` models early retirement.
Read this before touching the retirement service, the retirement routes,
the `retirement/` frontend components, or the demo retirement goal.

## Everything is computed in REAL terms (today's shekels)

- The user enters a **nominal** expected return and an inflation rate; the
  service converts to a real rate via `(1 + nominal) / (1 + inflation) - 1`
  (`_real_rate`) — per scenario (baseline, ±1% optimistic/conservative).
- Expenses, savings, pension, Bituach Leumi and passive income are held
  **constant** across the horizon (salaries and Israeli pension/BL payouts
  are CPI-indexed in practice).
- The FIRE number (`annual expenses / withdrawal rate`) is therefore
  directly comparable to any point of the projection, and the **constant
  horizontal FIRE-target line** on the net worth chart is correct.
- Do NOT reintroduce nominal growth or per-year inflation multipliers into
  one side only — the pre-2026-07 bug was exactly that mix (nominal net
  worth vs today-shekels FIRE number, inflating expenses vs frozen
  incomes), which declared FIRE years too early.

## Keren Hishtalmut — counted exactly once (the double-count trap)

**Scraped KH policies ARE part of the tracked net worth.** The data flow
that makes this true is easy to miss because it never touches the
analysis layer directly:

```
scrape → insurance_accounts (policy_type='hishtalmut')
       → InsuranceSyncMixin.sync_from_insurance
         (backend/services/investments/insurance_sync.py, called from
          backend/scraper/adapter.py + the insurance backfill route)
       → auto-creates an Investment (type='hishtalmut',
         insurance_policy_id set) with a 'scraped' balance snapshot
       → get_net_worth_over_time values investments snapshot-first
       → KH balance is inside status["net_worth"]
```

The retirement goal ALSO stores a user-facing `keren_hishtalmut_balance`
(auto-fillable from the same scraped data), which the projection models
as its own tax-free bucket (drawn first in retirement).

To count KH exactly once for **both** user flows,
`get_current_status` exposes `tracked_kh_value` — the current
snapshot-resolved value of open `type='hishtalmut'` investments — and
every wealth computation (projection base, progress %, solvers,
required savings) uses:

```
base_portfolio = net_worth - tracked_kh_value      # remove synced KH
total_wealth   = base_portfolio + goal.keren_hishtalmut_balance
```

- **Scraped user (designed flow, demo):** synced value ≈ goal balance →
  swap-out + bucket-in nets to `net_worth`; no double count.
- **Manual-entry user (never scraped):** `tracked_kh_value` is 0 → the
  typed KH balance counts on top of net worth.

Never subtract `goal.keren_hishtalmut_balance` from net worth directly
(drops KH for manual users), and never add it on top without the
`tracked_kh_value` swap (double-counts it for scraped users). Both bugs
have shipped; regression tests pin both flows in
`tests/backend/unit/test_retirement_service.py` (`TestRealTermsModel`).

## Readiness and the solver predicate

- `readiness == "on_track"` requires BOTH: baseline projection reaches the
  FIRE number **by the target retirement age**, AND the portfolio never
  depletes during drawdown within life expectancy.
- The suggestion solvers (`_solve_return_rate`, `_solve_monthly_expenses`,
  `_solve_target_retirement_age`) binary-search against the same
  `_plan_on_track` predicate — **never against drawdown survival alone**.
  A pension-covered plan survives at ANY return rate, so a survival-only
  search converges to the -10% floor and suggests nonsense.
- `_solve_life_expectancy` returns -1 when FIRE is never reached by the
  target age (a shorter life expectancy can't fix that).
- Solvers and projections both go through `_effective_status(goal)`, which
  applies the goal's net-worth/income/expenses overrides — suggestions
  must stay consistent with the projections shown next to them.

## monthly_savings_needed is ADDITIONAL, not total

`_calc_required_monthly_savings` credits the future value of current
total wealth AND of the contributions the user already makes
(`monthly_savings + keren_hishtalmut_monthly_contribution`), then
converts only the remaining gap into an extra payment. An on-track plan
reports 0 (the UI renders that as "On track!"). It uses the same
end-of-year annual-deposit model as `_project_net_worth`, so "0 extra"
agrees with the projection reaching FIRE at the target age.

## Demo Mode invariant

The demo retirement plan must stay **on_track** (green readiness, FIRE
age ≤ 55, 0 extra savings needed) — the dashboard-card e2e asserts it.
See `.claude/skills/demo-data-generation/SKILL.md` → retirement section
for the tuned goal params and how to re-verify after changing demo data
or calculator math.
