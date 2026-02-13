# Bank Balance & Prior Wealth Feature

## Overview

Add "Current Balance" functionality to bank accounts on the Data Sources page. When a user enters their current bank balance, the system calculates a fixed "Prior Wealth" anchor representing money that existed before tracking began. After each scrape, the balance is recalculated from this anchor. Bank balances are visualized as KPI cards on the Dashboard.

## Data Model

**New table: `bank_balances`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `provider` | String | e.g. "hapoalim" |
| `account_name` | String | User's display name |
| `balance` | Float | Current balance (recalculated on scrape) |
| `prior_wealth_amount` | Float | Fixed anchor, set when user enters balance |
| `last_manual_update` | String | Date user last entered/updated balance |
| `last_scrape_update` | String | Date balance was last recalculated from scrape |
| `created_at` / `updated_at` | DateTime | TimestampMixin |

**Rules:**
- One row per account (provider + account_name unique combo)
- No row = prior wealth is 0, no balance shown on dashboard

## Core Logic

### User enters balance
1. `prior_wealth = entered_balance - sum(all scraped bank txns for that account)`
2. `balance = entered_balance`
3. `last_manual_update = today`

### Scrape completes
1. `balance = prior_wealth (fixed) + sum(all scraped bank txns for that account)`
2. `last_scrape_update = today`
3. `prior_wealth` stays constant

### Guard
- User can only set balance if last successful scrape for that account is today. This ensures the txn sum is current when computing prior wealth.

## Backend Architecture

### New files
- `backend/models/bank_balance.py` — ORM model
- `backend/repositories/bank_balance_repository.py` — CRUD for bank_balances table
- `backend/services/bank_balance_service.py` — balance/prior wealth calculation logic
- `backend/routes/bank_balance_routes.py` — API endpoints

### API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/bank-balances` | Get all bank balances |
| `POST` | `/api/bank-balances` | Set balance for an account (body: provider, account_name, balance) |

### Service Methods
- `set_balance(provider, account_name, balance)` — calculates prior_wealth, creates/updates row, validates last scrape is today
- `recalculate_balance(provider, account_name)` — called after scrape, updates balance = prior_wealth + sum(txns)
- `get_all_balances()` — returns all balance records

### Integration Points
- **ScrapingService:** After successful scrape, call `bank_balance_service.recalculate_balance()` for the scraped account if a balance row exists.
- **AnalysisService:** `get_sankey_data()` sums prior wealth from both manual investments (existing) AND bank balances (new) into the same "Prior Wealth" Sankey source node.
- **CredentialsService:** On account disconnect/delete, clean up the corresponding balance row.

## Frontend — Data Sources Page

### Inline balance on each bank account row
- Balance display on the right side of each bank row (current balance or "No balance set")
- "Set Balance" button/icon that opens an inline input + confirm/cancel
- Button disabled with tooltip if last scrape date is not today ("Scrape today first to set balance")
- On submit, calls `POST /api/bank-balances`

### Data requirements
- Last scrape dates: existing `GET /api/scraping/last-scrapes`
- Balances: new `GET /api/bank-balances`

## Frontend — Dashboard Page

### New "Bank Balances" section
- Positioned below the existing 4 KPI cards, with a section header
- One card per bank account that has a balance, showing: account name, provider, formatted balance
- A "Total Bank Balance" summary card summing all account balances
- Same `StatCard` style, `Landmark` icon, distinct color (amber/gold)
- Section hidden entirely if no balances exist

### Data
- Fetched from `GET /api/bank-balances` via a TanStack Query hook

## Analysis Integration

- Bank prior wealth feeds into the existing "Prior Wealth" Sankey source node alongside manual investments prior wealth
- Categorized as "Other Income" for income/expense calculations
- No synthetic DB rows — injected virtually by AnalysisService

## Error Handling & Edge Cases

| Scenario | Behavior |
|----------|----------|
| Last scrape isn't today | Set Balance button disabled with tooltip |
| User sets balance, then scrapes again | Balance recalculated: prior_wealth + sum(new txns) |
| Account disconnected | Balance row cleaned up |
| Fresh scrape with 0 transactions | Prior wealth = entered balance |
| User re-enters balance | Prior wealth recalculated, row overwritten |
| No balance ever set | Prior wealth = 0, no dashboard card |
