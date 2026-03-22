# Early Retirement Calculator — Implementation Plan

## Overview

A new "Early Retirement" page in the finance dashboard that helps users plan for early retirement (פרישה מוקדמת) in the Israeli context. The page combines **user-defined goals** with **real data from the dashboard** (investments, income, expenses) to provide actionable insights and projections.

Inspired by Israeli tools like [Zeke Stories מחשבון פרישה מוקדמת](https://zekestories.com/calculators/retire_calc/), [חתול פיננסי](https://moneyplan.co.il/retirement-planning-for-early-retirement/), and international FIRE calculators like [Engaging Data](https://engaging-data.com/fire-calculator/) and [ProjectionLab](https://projectionlab.com/fire).

---

## Israeli Financial Landscape — Key Concepts to Model

### Savings Vehicles (ordered by withdrawal priority for early retirees)
1. **Taxable accounts** (חשבון מסחר) — liquid, capital gains taxed at 25%
2. **Keren Hishtalmut** (קרן השתלמות) — tax-free after 6 years, ~10% of salary (7.5% employer + 2.5% employee)
3. **Pension fund** (קרן פנסיה / ביטוח מנהלים) — locked until age 60 (early) or 67 (full), mandatory ~18-21% of salary
4. **Kupat Gemel** (קופת גמל) — long-term savings, various withdrawal rules
5. **Bituach Leumi** (ביטוח לאומי) — state old-age pension starting at age 67 (men) / 62-65 (women), ~₪2,500-3,500/month base

### Key Israeli-Specific Considerations
- **Retirement ages:** Legal retirement age 67 (men), 62-65 (women, transitioning to 65). Early retirement possible from age 60 with reduced benefits
- **Pension payout:** Monthly annuity from accumulated pension, not lump sum
- **Tax-free Keren Hishtalmut:** Critical bridge fund for the gap between early retirement and pension age
- **4% rule adjusted:** Israeli inflation, NIS-denominated, consider 3-3.5% for conservative planning
- **Two-phase retirement:** Phase 1 (early retirement → age 60/67) funded by liquid savings; Phase 2 (67+) supplemented by pension + Bituach Leumi

---

## Feature Design

### Page Layout: Three Sections

#### Section 1: Retirement Profile (Setup / Goals)
User configures their retirement parameters. Stored in a new `retirement_goals` DB table.

**Input fields:**
| Field | Type | Description |
|-------|------|-------------|
| `current_age` | int | User's current age |
| `target_retirement_age` | int | Goal: retire at this age (default: 50) |
| `life_expectancy` | int | Plan for this many years (default: 90) |
| `monthly_expenses_in_retirement` | float | Expected monthly spend in retirement (₪) |
| `inflation_rate` | float | Annual inflation assumption (default: 2.5%) |
| `expected_return_rate` | float | Annual real return on investments (default: 4%) |

**Israeli savings vehicles (optional, for more accurate projections):**
| Field | Type | Description |
|-------|------|-------------|
| `pension_monthly_payout_estimate` | float | Expected monthly pension at age 67 (₪) |
| `keren_hishtalmut_balance` | float | Current Keren Hishtalmut balance (₪) |
| `keren_hishtalmut_monthly_contribution` | float | Monthly contribution to KH (₪) |
| `bituach_leumi_eligible` | bool | Will receive Bituach Leumi old-age pension |
| `bituach_leumi_monthly_estimate` | float | Expected monthly BL pension (default: ₪2,800) |
| `other_passive_income` | float | Rental income, etc. (₪/month) |

#### Section 2: Status Dashboard (Auto-Populated from Existing Data)
Pulls real data from the dashboard to show current financial position:

- **Current net worth** — from `AnalysisService.get_net_worth_over_time()` (latest data point)
- **Average monthly expenses** — from `AnalysisService.get_income_investments_and_expenses()` (last 6-12 months)
- **Average monthly income** — same source
- **Current savings rate** — `(income - expenses) / income * 100`
- **Total investment portfolio** — from `InvestmentsService` (open investments)
- **Monthly investment contributions** — from recent investment transactions

These are **read-only insights** — the user doesn't input them; they come from their actual tracked data.

#### Section 3: Projections & Insights
Calculated results displayed as cards + charts:

**KPI Cards:**
| KPI | Calculation |
|-----|-------------|
| **FIRE Number** | `annual_expenses_in_retirement / withdrawal_rate` (where withdrawal_rate = expected_return_rate or custom, typically 3.5-4%) |
| **Years to FIRE** | Compound growth projection: how many years until `net_worth + future_savings` ≥ FIRE number |
| **FIRE Age** | `current_age + years_to_fire` |
| **Monthly Savings Needed** | If current trajectory won't meet goal, how much to save monthly |
| **Progress %** | `current_net_worth / fire_number * 100` |
| **Retirement Readiness** | Traffic light: 🔴 off track, 🟡 close, 🟢 on track |

**Charts (using Plotly, consistent with rest of app):**

1. **Net Worth Projection Chart** (line chart)
   - X: age (current → life_expectancy)
   - Y: projected net worth (₪)
   - Lines: optimistic / baseline / conservative scenarios
   - Vertical markers: target retirement age, pension start age (60/67), Bituach Leumi age
   - Horizontal marker: FIRE number threshold

2. **Retirement Income Waterfall** (stacked area or bar)
   - Shows income sources by phase:
     - Phase 1 (early retirement → 60): Portfolio withdrawals only
     - Phase 2 (60 → 67): Portfolio + Pension (if early pension elected)
     - Phase 3 (67+): Portfolio + Full Pension + Bituach Leumi
   - Compared against monthly expense line

3. **Savings Rate Gauge** (semi-gauge, reusing existing `SemiGauge` component)
   - Current savings rate vs. required savings rate to hit FIRE target

---

## Backend Architecture

### New Model: `RetirementGoal`
```
Table: retirement_goals (single row — one profile per user)
─────────────────────────────────────────
id                              INTEGER PK
current_age                     INTEGER NOT NULL
target_retirement_age           INTEGER NOT NULL DEFAULT 50
life_expectancy                 INTEGER NOT NULL DEFAULT 90
monthly_expenses_in_retirement  FLOAT NOT NULL
inflation_rate                  FLOAT NOT NULL DEFAULT 0.025
expected_return_rate            FLOAT NOT NULL DEFAULT 0.04
withdrawal_rate                 FLOAT NOT NULL DEFAULT 0.035
pension_monthly_payout_estimate FLOAT DEFAULT 0
keren_hishtalmut_balance        FLOAT DEFAULT 0
keren_hishtalmut_monthly_contribution FLOAT DEFAULT 0
bituach_leumi_eligible          BOOLEAN DEFAULT 1
bituach_leumi_monthly_estimate  FLOAT DEFAULT 2800
other_passive_income            FLOAT DEFAULT 0
created_at                      DATETIME
updated_at                      DATETIME
```

### New Files (Backend)
| File | Purpose |
|------|---------|
| `backend/models/retirement_goal.py` | SQLAlchemy model |
| `backend/repositories/retirement_goal_repository.py` | CRUD for the single-row retirement profile |
| `backend/services/retirement_service.py` | All projection calculations |
| `backend/routes/retirement.py` | API endpoints |

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/retirement/goal` | Get retirement goal (or null if not set) |
| `PUT` | `/api/retirement/goal` | Create or update retirement goal |
| `GET` | `/api/retirement/status` | Get current financial status (auto-populated from real data) |
| `GET` | `/api/retirement/projections` | Get FIRE calculations and projection data |

### Service: `RetirementService`
Dependencies: `AnalysisService`, `InvestmentsService`, `BankBalanceService`, `CashBalanceService`, `RetirementGoalRepository`

**Key methods:**

1. **`get_current_status()`** — Aggregates real dashboard data:
   - Pulls net worth, avg expenses, avg income, savings rate, investment totals
   - Returns dict with current financial snapshot

2. **`get_projections(goal)`** — Core calculation engine:
   - Computes FIRE number based on goal parameters
   - Projects net worth growth year-by-year considering:
     - Current savings trajectory (from real data)
     - Keren Hishtalmut growth (tax-free, separate bucket)
     - Investment returns
     - Inflation-adjusted expenses
   - Three scenarios: optimistic (return +1%), baseline, conservative (return -1%)
   - Identifies FIRE age and years to FIRE
   - Calculates monthly savings needed if off track

3. **`get_retirement_income_projection(goal)`** — Phase-based income:
   - Phase 1: portfolio withdrawals + other passive income
   - Phase 2: + pension (if age ≥ 60)
   - Phase 3: + Bituach Leumi (if age ≥ 67)
   - Year-by-year income vs. inflation-adjusted expenses

---

## Frontend Architecture

### New Files
| File | Purpose |
|------|---------|
| `frontend/src/pages/EarlyRetirement.tsx` | Main page, composes sections |
| `frontend/src/components/retirement/RetirementGoalForm.tsx` | Goal setup form |
| `frontend/src/components/retirement/RetirementStatus.tsx` | Auto-populated current status cards |
| `frontend/src/components/retirement/RetirementProjections.tsx` | KPI cards + charts |
| `frontend/src/components/retirement/NetWorthProjectionChart.tsx` | Plotly projection chart |
| `frontend/src/components/retirement/RetirementIncomeChart.tsx` | Plotly income waterfall |

### State Management
- TanStack Query for all API calls (`useQuery` for GET, `useMutation` for PUT)
- No Zustand needed — all state is server-derived

### Routing
- Add route: `/early-retirement` → `<EarlyRetirement />`
- Add sidebar entry with icon

### i18n
- Add `earlyRetirement` section to both `en.json` and `he.json`
- All user-visible strings via `t("earlyRetirement.xxx")`
- RTL-aware layout with logical properties

---

## Implementation Steps

### Phase 1: Backend Foundation
1. Run `scaffold_feature.py retirement_goal` to generate boilerplate
2. Customize model with all fields from the schema above
3. Implement repository (upsert pattern — single row)
4. Implement `RetirementService` with calculation methods
5. Wire up routes with Pydantic request/response schemas
6. Register in `main.py`, add table to constants
7. Write unit tests for projection calculations

### Phase 2: Frontend — Goal Form & Status
8. Create page skeleton with three sections
9. Build `RetirementGoalForm` with all input fields (grouped: basic, Israeli vehicles)
10. Add API methods to `api.ts`
11. Build `RetirementStatus` cards pulling real data
12. Register route in `App.tsx`, add sidebar entry

### Phase 3: Frontend — Projections & Charts
13. Build KPI cards (FIRE number, years to FIRE, progress %, readiness indicator)
14. Build `NetWorthProjectionChart` (multi-line with scenario bands)
15. Build `RetirementIncomeChart` (stacked phases)
16. Build savings rate gauge
17. Add i18n keys (en + he)

### Phase 4: Polish
18. Empty state: show setup wizard when no goal is configured yet
19. Responsive layout, RTL testing
20. Edge cases: no transaction data yet, zero income, already past target age
