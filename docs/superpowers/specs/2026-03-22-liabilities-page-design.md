# Liabilities Page — Design Spec

## Overview

Add a Liabilities page to track loans and debts. A `Liability` record is a metadata layer on top of existing transactions — no new transaction table. Transactions are matched by `category="Liabilities"` + tag. The system calculates amortization schedules, remaining balances, and compares expected vs actual payments.

**Scope:** Fixed interest rate loans with fixed monthly payments. Future iterations will add mashkanta (mortgage) support, variable rates, and a loan calculator.

## Data Model

### `liabilities` table

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | Integer | PK, auto-increment |
| `name` | String | Not null |
| `lender` | String | Nullable |
| `category` | String | Not null, always "Liabilities" |
| `tag` | String | Not null |
| `principal_amount` | Float | Not null |
| `interest_rate` | Float | Not null (annual %, e.g., 4.5) |
| `term_months` | Integer | Not null |
| `start_date` | Date | Not null |
| `is_paid_off` | Boolean | Default false (stored as 0/1 in SQLite) |
| `paid_off_date` | Date | Nullable |
| `notes` | Text | Nullable |
| `created_date` | Date | Auto-set to today |

**Unique constraint:** `(category, tag)` — mirrors the investment pattern.

### Transaction Matching

No dedicated transaction table. Transactions are fetched from existing tables (bank, cash, credit card) filtered by:
- `category = "Liabilities"`
- `tag = liability.tag`

Amount convention:
- **Positive** (`amount > 0`): loan receipt / disbursement
- **Negative** (`amount < 0`): repayment

### Calculated Fields (service layer, not stored)

- **Monthly payment:** Standard fixed-rate amortization formula: `P * r(1+r)^n / ((1+r)^n - 1)` where P = principal, r = monthly rate, n = term months
- **Remaining balance:** `principal + total_accrued_interest - abs(sum of negative transactions)`
- **Total interest cost:** `monthly_payment * term_months - principal`
- **Amortization schedule:** List of monthly entries with payment number, date, principal portion, interest portion, remaining balance
- **Actual vs expected:** Match actual transactions to schedule months, show deviations

## Backend Architecture

### Repository (`liabilities_repository.py`)

- `create_liability(name, lender, tag, principal_amount, interest_rate, term_months, start_date, notes)` → creates record
- `get_all_liabilities(include_paid_off=False)` → DataFrame
- `get_by_id(id)` → DataFrame
- `update_liability(id, **fields)` → update fields
- `mark_paid_off(id, paid_off_date)` → set `is_paid_off=1`, `paid_off_date`
- `reopen(id)` → set `is_paid_off=0`, clear `paid_off_date`
- `delete_liability(id)` → delete record
- `get_transactions_for_liability(tag)` → query across bank/cash/credit card tables where `category="Liabilities"` and `tag=tag`, return DataFrame

### Service (`liabilities_service.py`)

- `get_all_liabilities(include_paid_off=False)` → list with calculated metrics (remaining balance, monthly payment, % paid off)
- `get_liability(id)` → single liability with full calculated details
- `create_liability(...)` → creates record, auto-creates tag under Liabilities category if it doesn't exist
- `update_liability(id, ...)` → delegates to repo
- `mark_paid_off(id, paid_off_date)` → marks as paid off
- `reopen(id)` → reactivates
- `delete_liability(id)` → deletes record
- `get_liability_analysis(id)` → returns amortization schedule + actual vs expected payment data
- `get_liability_transactions(id)` → matched transactions from existing tables
- `calculate_amortization_schedule(principal, rate, term, start_date)` → pure math function, returns list of `{payment_number, date, payment, principal_portion, interest_portion, remaining_balance}`

### Routes (`/api/liabilities/`)

```
GET    /api/liabilities/                    # List all (query param: include_paid_off)
GET    /api/liabilities/{id}                # Get one with calculated metrics
POST   /api/liabilities/                    # Create
PUT    /api/liabilities/{id}                # Update
POST   /api/liabilities/{id}/pay-off        # Mark paid off (body: paid_off_date)
POST   /api/liabilities/{id}/reopen         # Reactivate
DELETE /api/liabilities/{id}                # Delete
GET    /api/liabilities/{id}/analysis       # Amortization + actual vs expected
GET    /api/liabilities/{id}/transactions   # Matched transactions
```

### Pydantic Schemas (inline in routes)

```python
class LiabilityCreate(BaseModel):
    name: str
    lender: str | None = None
    tag: str
    principal_amount: float
    interest_rate: float
    term_months: int
    start_date: date
    notes: str | None = None

class LiabilityUpdate(BaseModel):
    name: str | None = None
    lender: str | None = None
    interest_rate: float | None = None
    paid_off_date: date | None = None
    notes: str | None = None
```

## Frontend

### Page (`Liabilities.tsx`) — Card Grid Layout

**Header section:**
- Page title + subtitle
- "Add Liability" button (opens create modal)

**Summary stat cards (3 cards):**
- Total Outstanding Debt (sum of remaining balances, red)
- Total Monthly Payments (sum of monthly payments)
- Total Interest (paid so far + projected remaining, amber)

**Liability cards grid:**
Each card shows:
- Name + lender + status badge (Active / Paid Off)
- Rate, term, start date metadata line
- Progress bar (% of principal paid off)
- Remaining balance + monthly payment
- Action buttons: view analysis, edit, mark paid off, delete

Paid-off liabilities shown with reduced opacity (like closed investments).

**Analysis modal** (opened from card):
- Amortization schedule table: month, payment, principal portion, interest portion, remaining balance
- Actual vs expected comparison: highlight months where actual payment differs from expected
- Summary metrics: total paid, total interest paid, interest remaining
- Transaction list: matched transactions from bank/cash tables

**Create/Edit modal:**
- Form fields matching LiabilityCreate schema
- Tag field with autocomplete from existing Liabilities tags + free text for new tags

### Navigation

Add "Liabilities" to sidebar between Investments and Insurance.

### i18n

Add `liabilities.*` section to both `en.json` and `he.json`:
- Hebrew page title: "התחייבויות"
- All user-visible strings via `t("liabilities.key")`

### API Service

Add `liabilitiesApi` to `frontend/src/services/api.ts` following existing patterns (investments, insurance).

## KPI Impact

No changes to existing KPI calculations. The Liabilities category behavior in the analysis service remains unchanged:
- Positive Liabilities → income (loan receipts)
- Negative Liabilities → expenses (repayments)
- Sankey diagram already shows "Loans" as income source

The Liabilities page is a dedicated tracking view, not a change to how liabilities flow through KPIs.

## Future Iterations (out of scope for v1)

- Mashkanta (mortgage) support with variable rates, CPI-linked tracks
- Loan calculator (simulate loans before taking them)
- Early repayment scenarios
- Multiple rate types (variable, prime-linked, CPI-linked)
- Scraper integration for auto-fetching loan balances
