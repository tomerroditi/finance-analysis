---
paths:
  - "backend/services/retirement_service.py"
  - "backend/routes/retirement.py"
  - "backend/models/retirement_goal.py"
  - "backend/services/investments/insurance_sync.py"
  - "frontend/src/components/retirement/**/*.{ts,tsx}"
---
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

## The status baselines are MEDIANS, not means

`get_current_status` derives `avg_monthly_income` (6 complete months) and
`avg_monthly_expenses` (12 complete months) from
`get_income_expenses_over_time`, and takes the **median** of each window.

`monthly_savings = avg_monthly_income - avg_monthly_expenses` is then
compounded for the whole horizon, so one freak month is not a rounding error
in this model — it moves the FIRE date, the savings rate, `monthly_savings_needed`
and every solver suggestion. A mean did exactly that: an inheritance banked in
one month read as ₪108k/month income and a 65% savings rate against a ₪25k
salary. A windfall is not a salary, and a wedding is not a cost of living;
the number that survives one is the middle month.

Don't "simplify" either side back to `sum(...) / len(...)`. Pinned by
`TestCurrentStatusBaselines`.

## Keren Hishtalmut — counted exactly once (the double-count trap)

**Both scraped AND manually-created KH investments are part of the
tracked net worth.** The data flow that makes this true is easy to miss
because it never touches the analysis layer directly — there are two
paths into the same `type='hishtalmut'` investment pool:

```
Path A (scraped):
  scrape → insurance_accounts (policy_type='hishtalmut')
         → InsuranceSyncMixin.sync_from_insurance
           (backend/services/investments/insurance_sync.py, called from
            backend/scraper/adapter.py + the insurance backfill route)
         → auto-creates an Investment (type='hishtalmut',
           insurance_policy_id set) with a 'scraped' balance snapshot

Path B (manual):
  Investments page → create Investment (type='hishtalmut',
                      insurance_policy_id = None)

Both paths converge:
  Investment (type='hishtalmut') → get_net_worth_over_time values
    investments snapshot-first → KH balance is inside status["net_worth"]
```

The retirement goal ALSO stores a user-facing `keren_hishtalmut_balance`
(auto-fillable from the same scraped/manual data), which the projection
models as its own tax-free bucket (drawn first in retirement).

`InvestmentsService.get_hishtalmut_total_balance()` is the single source
of truth for both halves of the swap below: it sums the current
snapshot-resolved balance of every open `type='hishtalmut'` investment,
scraped or manually-created alike, and backs both `get_current_status`'s
`tracked_kh_value` and `get_scraped_defaults`'s auto-filled
`keren_hishtalmut_balance`. To count KH exactly once for **every** user
flow, `get_current_status` exposes `tracked_kh_value` from that method —
the current snapshot-resolved value of open `type='hishtalmut'`
investments — and every wealth computation (projection base, progress %,
solvers, required savings) uses:

```
base_portfolio = net_worth - tracked_kh_value      # remove tracked KH
total_wealth   = base_portfolio + goal.keren_hishtalmut_balance
```

- **Scraped user (designed flow, demo):** synced value ≈ goal balance →
  swap-out + bucket-in nets to `net_worth`; no double count.
- **Manual-entry user (typed `type='hishtalmut'` investment, never
  scraped):** `tracked_kh_value` also reflects that investment's balance
  (via `get_hishtalmut_total_balance()`) → the same swap-out + bucket-in
  applies, and it counts exactly once.

Never subtract `goal.keren_hishtalmut_balance` from net worth directly
(drops KH for manual users), and never add it on top without the
`tracked_kh_value` swap (double-counts it for scraped and manual users
alike). Both bugs have shipped; regression tests pin both flows in
`tests/backend/unit/test_retirement_service.py` (`TestRealTermsModel`).

## Readiness and the solver predicate

Readiness is a **four**-state ladder, and solvency is the gate — running
out of money is the only real failure, so it is checked first and
independently of the FIRE number:

| state | meaning |
|---|---|
| `off_track` | portfolio depletes before life expectancy (regardless of FIRE) |
| `on_track` | solvent, and FIRE reached **by the target retirement age** |
| `close` | solvent, and FIRE reached within **target age + 5** |
| `funded` | solvent, but FIRE never reached in that window |

`funded` exists because the FIRE number (`annual expenses / withdrawal
rate`) assumes the portfolio funds **100%** of retirement spending
forever — it never nets out pension, Bituach Leumi or passive income,
even though the drawdown projection credits all three. An Israeli plan
whose pension + BL cover most of retirement spending is therefore solvent
to life expectancy while never accumulating ~28x expenses. That case used
to fall through to `off_track`, which read as failure for a plan that
never runs dry.

Note pension and Bituach Leumi only start at `full_pension_age` (67 male
/ 65 female). Retiring earlier leaves a gap the portfolio must bridge
alone, so an early target age can deplete even when guaranteed income
would later exceed spending — that is genuinely `off_track`.

**`_plan_on_track` (the solver predicate) keeps the STRICT definition** —
FIRE by the target age AND survival. It is deliberately narrower than
"not off_track"; see the next bullet for why.
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

## Status overrides must stay live, not frozen

The goal's snapshot overrides (`net_worth_override`, `monthly_income`,
`monthly_expenses_override`, `total_investments_override`) mean "replace
the calculated value with this number". The form (`RetirementGoalForm`)
therefore **sends `null` for any snapshot field equal to the calculated
status value** (`formToPayload`'s `normalizeOverride`). Never "simplify"
that into sending the displayed number — that froze every saved plan at
its save-day snapshot (net worth/income/expenses stopped responding to
new transactions, and the reset arrow couldn't undo it). The
`retirement-snapshot-fields` e2e pins the null-for-untouched behavior on
the save request body. Note `total_investments_override` was removed from
the form entirely (no projection math ever consumed it — the whole net
worth compounds at the expected return); the form always sends it as
null so legacy stored overrides get cleared.

## Other UI contracts

- `full_pension_age` (gender-resolved, 67 male / 65 female) is part of the
  projections response — the net-worth chart's pension-age marker must use
  it, never a hardcoded 67.
- Scraped `pension_monthly_deposit` (the ~2k monthly contribution INTO the
  fund) must never be auto-filled into `pension_monthly_payout_estimate`
  (the expected monthly payout, typically 4-5× larger). That autofill
  shipped once and seeded materially wrong retirement income.
- Solvers return **-1** for "not solvable" (target age at/behind current
  age, nothing on-track at any value) — never 0, which the UI would render
  as a real suggestion.
- "On track!" copy for `monthly_savings_needed == 0` renders only when
  `readiness == "on_track"` — 0 extra savings can coexist with off_track
  (FIRE reached but the portfolio depletes in drawdown).

## The pension payout offered from the funds' own forecasts

`pension_monthly_payout_estimate` is still user-entered, but the form now
*offers* a figure: a "Use the funds' forecast for retiring at N" button under
the field, fed by `GET /retirement/pension-forecast`
(`RetirementService.get_pension_forecast`). It is never auto-applied — the
user's own statement figure wins until they click.

The figure comes from the pension clearing house, which publishes per pension
fund the capital and monthly pension at retirement age **both** with deposits
continuing and with deposits stopping today (`insurance_accounts.details`,
see `InsuranceAccountService.get_pension_forecasts`). Deposits really stop at
`target_retirement_age`, somewhere in between, so `project_pension_payout`
re-derives each fund's pension for that age from its own two figures:

- the fund's growth factor is the one that turns today's balance into the
  no-deposit capital over the years to its retirement age;
- a deposit stream stopped after `k` of `N` years is worth the share
  `(g^k − 1) / (g^N − 1) × g^(N − k)` of the gap between the two forecasts;
- that share of the gap between the two *pensions* is added to the
  no-deposit pension (interpolating pensions, not capitals, keeps both ends
  exact when the provider's two annuity factors differ in their last digit).

Stopping at retirement age reproduces the provider's "deposits continue"
figure, stopping today its "no further deposits" figure — pinned by
`TestProjectPensionPayout`. The provider's assumptions (real terms, its own
return and fees, its annuity factor) carry over unchanged. Every fund is
projected with the plan holder's ages, so a household plan that also holds a
spouse's fund treats it as the holder's — the demo does exactly that.

Keep the existing guard intact: the scraped `pension_monthly_deposit` must
never be written into `pension_monthly_payout_estimate` — that autofill
shipped once and seeded materially wrong retirement income. The forecast is a
projected *payout*, not the deposit.

## Demo Mode invariant

The demo retirement plan must stay **on_track** (green readiness, FIRE
age ≤ 55, 0 extra savings needed) — the dashboard-card e2e asserts it.
See `.claude/skills/demo-data-generation/SKILL.md` → retirement section
for the tuned goal params and how to re-verify after changing demo data
or calculator math.
