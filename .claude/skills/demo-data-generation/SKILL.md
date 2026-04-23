---
name: demo-data-generation
description: Use when modifying, extending, or regenerating the demo SQLite database that powers Demo Mode and the test fixtures. Covers the story the data tells (the Cohen family), the conventions every new record must follow, and — critically — how each individual's pension and Keren Hishtalmut deposits are derived from their gross salary under Israeli law. Triggers on "demo data", "regenerate demo", "add demo transaction", "demo fixture", "generate_demo_data", "Cohen family", "demo pension", "demo KH", "demo keren hishtalmut".
---

# Demo Data Generation

The demo database (`backend/resources/demo_data.db`) is produced by a single script — `scripts/generate_demo_data.py` — and is the dataset users see when they toggle **Demo Mode** in the UI. It also backs many UI-level smoke tests. Regenerate with:

```bash
poetry run python scripts/generate_demo_data.py
```

## The story the data tells

The dataset models **the Cohens**, a dual-income Israeli couple with two kids (one in daycare, one in elementary school) who own an apartment, save steadily every month, take an annual family vacation, and are **planning their wedding** in the last ~10 months of the tracked period.

| Span | `START_DATE = REFERENCE_DATE − 3 years − 1 day` → `REFERENCE_DATE` |
|---|---|
| Reference date | 2026-02-25 (hard-coded) |
| Tracked window | Feb 2023 → Feb 2026 (3 years) |

### Household cashflow
- **Two salaries deposited monthly** to the primary bank account:
  - *Tech Company* (1st of the month) — net ≈ 18,000 (gross **22,000**)
  - *School District* (5th of the month) — net ≈ 12,000 (gross **14,000**)
- **Annual Tech bonus** every December (~30k)
- Occasional **freelance income** (3–4 months per year)
- One-time **Prior Wealth** deposit early in the tracked window (tagged `Other Income / Prior Wealth`)

### Monthly fixed outflows
- Mortgage (Liabilities / Mortgage) — constant amortization payment
- Car loan (received mid-period, then monthly payments)
- CC bill payments (Max + Visa Cal), posted on the 2nd of the following month with small ±2–3% variance vs. the itemized totals — this is the source of the "CC gap" in the Sankey
- Standing orders every other month (Bituach Leumi / Arnona)
- Monthly transfer from *hapoalim* Main Account → *leumi* Savings Account (tagged `Ignore / Internal Transactions`)

### Seasonal patterns (deliberate, so charts look "alive")
- **Summer vacation each August** — flights + hotel + on-trip food, rotating destination (Greece / Cyprus / Italy)
- **Short winter getaway each December** (domestic hotel)
- **Back-to-school supplies surge** in August/September
- **Holiday gifts** in December (Hanukkah) and March/April (Passover)
- **Kids birthday parties** in March and October
- **Annual car service** in the spring

### Long-running arcs
- **Investments** (manual, monthly): Stock Market Fund −2,000, Savings Plan −1,500, and a Corporate Bond that was deposited ~12 months ago and matured/withdrawn ~6 months ago (closed)
- **Home Renovation** transactions in the last 6 months (project budget: `Home Renovation`)
- **Wedding planning** in the last ~10 months (project budget: `Our Wedding`, 120,000 ILS across 7 tags — Venue, Catering, Photography, Attire, Rings, Invitations, Honeymoon). Small/medium vendor payments on the Max CC; large deposits (venue, catering) via bank transfer.
- **Paid-off Personal Loan** earlier in the window + active Mortgage + active Car Loan — exercises all three liability states.

### Other coverage guaranteed by the script
- Multiple bank accounts (hapoalim Main + leumi Savings) and multiple cash envelopes (Petty Cash + Kids Envelope)
- Untagged CC transactions so auto-tagging and manual-tagging flows can be demoed
- Splits across 2 sources (CC + cash) — a couple of CC parents converted into different categories
- 7 pending refunds covering all statuses (pending / partial / resolved / closed) + multi-link + auto-split + one `source_type='split'`
- Tagging rules exercising 5 different operators (`contains`, `equals`, `starts_with`, `less_than`, `between`)
- Budget rules: category-only, tag-level, and two project budgets (Home Renovation + Our Wedding) over the last 6 months
- 5 insurance accounts (see next section) + a `RetirementGoal` tied to them

---

## Pension and Keren Hishtalmut — the rules

This is the section most prone to drift. **Every individual's pension and KH deposits are derived from that individual's own gross salary** via the legally-defined percentages below. Each employee also has their **own separate pension and KH accounts** — they are never pooled. Treat the `generate_insurance_data` function as the single source of truth; keep balances and monthly contributions consistent with the percentages below if you touch any of them.

### Israeli compulsory-pension law (in force since 2017)

All percentages are applied to the employee's **gross** salary (the number before income tax and Bituach Leumi are deducted). Employer-side contributions are added **on top of** the gross salary — they are not taken from the employee's paycheck. Only the employee share appears as a deduction from the net figure that lands in the bank account.

**Pension (קרן פנסיה) — total 18.5% of gross:**

| Share | Label (code) | Label (UI / Hebrew) | Pct |
|---|---|---|---|
| Employee | `pn_employee_pct` | עובד (תגמולי עובד) | **6.0%** |
| Employer savings | `pn_employer_pct` | מעסיק (תגמולי מעסיק) | **6.5%** |
| Employer severance | `pn_severance_pct` | פיצויים | **6.0%** |
| **Total** | `pn_total_pct` | סה״כ הפקדה | **18.5%** |

Memo string written to every pension transaction:
`"עובד: {employee} / מעסיק: {employer_savings} / פיצויים: {severance}"` — the three numbers must sum to `amount`.

**Keren Hishtalmut (קרן השתלמות) — total 10% of gross:**

| Share | Code | Pct |
|---|---|---|
| Employee | `kh_employee_pct` | **2.5%** |
| Employer | `kh_employer_pct` | **7.5%** |
| **Total** | `kh_total_pct` | **10%** |

**KH tax-exempt cap (2024–2025): gross salary up to 15,712 ILS/month.** Deposits above the cap are taxable for the employee, and real-world payroll systems commonly cap KH deposits at this base. We follow that convention — so a high-earner's KH contribution is `min(gross, 15_712) × 10%`, *not* `gross × 10%`.

### How this maps to the demo couple

Both the Tech employee and the Teacher have their **own** pension account *and* their **own** KH account. The Tech employee additionally has a frozen KH account from a previous employer. No account is shared between spouses.

| Individual | Gross salary | Pension total | KH base (after cap) | KH total |
|---|---|---|---|---|
| Tech Company employee | **22,000** | `22,000 × 18.5% = 4,070` | `min(22,000, 15,712) = 15,712` | `15,712 × 10% = 1,571` |
| School District employee | **14,000** | `14,000 × 18.5% = 2,590` | `14,000` (no cap) | `14,000 × 10% = 1,400` |
| Tech — previous employer (frozen) | 12,000 (assumed) | — | `12,000` | `12,000 × 10% = 1,200` |

All derived numbers (individual shares, memo breakdowns, monthly totals) come from the same constants. If you bump a gross salary the rest of the account propagates automatically — don't hand-edit the monthly amounts and leave the percentages stale, and vice versa. The function comment at the top of `generate_insurance_data` is the canonical write-up of this.

### Account-balance calibration

Balances reflect approximately **5 years of contributions** (2 before the tracked window + 3 inside it) plus **~5–6%/yr real growth**:

```
balance ≈ monthly_contribution × 60 months × (1.13 .. 1.19 growth factor)
```

Use this as a sanity check whenever a balance is edited. If you change a monthly contribution or the gross salary it derives from, recompute the target balance with this rule of thumb. The `RetirementGoal` row's `keren_hishtalmut_balance` and `keren_hishtalmut_monthly_contribution` must equal the sum across the three KH accounts — they are already computed this way; don't hard-code them again.

### Yields on investment tracks

The per-track `yield_pct` values under `investment_tracks` JSON reflect **long-term realistic returns**, not cherry-picked single-year numbers. Stay in these ranges unless you have a specific reason:

| Track type | Realistic range |
|---|---|
| General / mixed pension track | 5–6% |
| Bonds-heavy track | 3–4% |
| Equity / S&P 500 track | 6–8% |
| Default (frozen, previous employer) | 4–5% |

---

## Generator structure

```
scripts/generate_demo_data.py
├── Constants: REFERENCE_DATE, START_DATE, DB_PATH, random.seed(42)
├── CATEGORIES_DATA, TAGGING_RULES_DATA
├── generate_cc_transactions        ← itemized CC (Max + Visa Cal), seasonal events, wedding CC vendors
├── generate_untagged_transactions  ← 8 deliberately-untagged CC entries for auto-tagging demos
├── generate_bank_transactions      ← salaries, mortgage, CC bills, bonuses, wedding bank transfers
├── generate_cash_transactions      ← Petty Cash + Kids Envelope
├── generate_investment_transactions
├── create_investments              ← 3 investments + prior-wealth recalc from transactions
├── create_investment_snapshots
├── create_budget_rules             ← last 6 months + 2 project budgets
├── create_split_transactions       ← 4 splits (3 CC + 1 cash)
├── create_bank_balance             ← 2 bank accounts
├── create_cash_balance             ← 2 cash envelopes
├── create_pending_refunds          ← 7 refunds covering all statuses + split source
├── create_liabilities              ← Mortgage, Car Loan, paid-off Personal Loan
├── create_retirement_goal          ← derives KH totals from insurance-account constants
├── create_scraping_history
├── generate_insurance_data         ← pension + KH per Israeli law (see rules above)
└── main()                          ← orchestrates, drops+recreates the DB, prints row counts
```

`random.seed(42)` is set at module load so every regeneration produces the same data — commits to the `.db` file stay deterministic. If you add new randomness, keep it seeded so diffs remain small.

---

## When to touch this script

Regenerate and commit the `.db` along with script edits whenever you:
- Add a new transaction pattern, story arc, or category that Demo Mode users should see
- Find a missing use case while auditing the data flow page (e.g., a new KPI that needs seed data)
- Fix a realism bug (wrong percentages, wrong category names, etc.)
- Add support for a new table (scaffold fixture rows alongside the schema change)

## When NOT to touch this script

- Never introduce non-seeded randomness
- Never hand-edit the `.db` file — always go through the script so the DB is reproducible
- Never hardcode monthly pension/KH amounts; derive them from a gross salary and the percentages above
- Never let `RetirementGoal.keren_hishtalmut_balance` drift from the sum of the three KH accounts

## After every change — checks

1. `poetry run python scripts/generate_demo_data.py` — must print non-zero row counts for every table it touches and end without exceptions.
2. `poetry run pytest tests/backend/ -x -q` — must stay green; the full suite does not depend on the exact numbers but does load the DB in some fixtures.
3. Sanity-check totals against the story (`SELECT SUM(amount) FROM ...`): salaries over 3 years should be ~1.2M; investments deposited ~125k; wedding paid ≥ 90k of the 120k budget; each pension/KH balance should sit within the `monthly × 60 × 1.13..1.19` band.
4. Commit the `.db` and the `.py` together so the bundled template always matches the generator.

## Common pitfalls

- **"Transport" vs "Transportation"** — the category is `Transportation`; writing `Transport` creates orphan rows that never render in the category pie chart. Auto-tagged transactions and refund back-payments have hit this bug before.
- **Date anchors that assume 14 months** — several thresholds (home renovation last 6 months, wedding last 10 months) were originally tied to a shorter window. When extending the span, verify each `timedelta(days=…)` still picks the intended slice.
- **CC bill variance** — bank CC bill amounts are deliberately `cc_total × uniform(0.98, 1.03)` so the Sankey's CC gap is non-zero. Don't "fix" this to exact totals.
- **Prior wealth in investments** — after any change to investment transactions, the per-investment `prior_wealth_amount` must be recalculated as `−sum(txns)`. The script does this in `create_investments`; don't bypass it.
- **Memo sum must equal transaction amount** — a pension deposit of 4,070 whose memo reads `עובד: 1320 / מעסיק: 1430 / פיצויים: 1320` is valid; if the three Hebrew fields don't sum to the `amount`, the UI will display an inconsistent breakdown.
