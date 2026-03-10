# Demo Mode Design

## Overview

Replace the existing "Test Mode" with a "Demo Mode" that loads a rich, pre-built dataset showcasing every app feature. Intended for investor presentations and potential user demos. All dates shift dynamically so charts always look current.

## Architecture

### Storage

- **Pre-built DB:** `backend/resources/demo_data.db` — committed to repo
- **Seed script:** `scripts/generate_demo_data.py` — generates the DB, run manually when updates needed
- **Demo categories:** `backend/resources/demo_categories.yaml` — committed alongside DB
- **Runtime location:** `~/.finance-analysis/demo_env/demo_data.db` (copied on activation)

### Activation Flow

```
User clicks "Demo Mode" toggle
  → POST /api/testing/toggle_demo_mode { enabled: true }
  → AppConfig.set_demo_mode(True)
  → database.reset_engine()
  → Copy demo_data.db → ~/.finance-analysis/demo_env/demo_data.db
  → Copy demo_categories.yaml → ~/.finance-analysis/demo_env/categories.yaml
  → Run date-shift SQL on copied DB
  → Seed demo credentials (test scrapers)
  → Return success
  → Frontend: queryClient.resetQueries()
```

### Date Shifting

The seed script generates data with a fixed **reference date** (stored as a constant in the shift logic). On activation, compute `offset_days = today - reference_date` and run:

```sql
UPDATE bank_transactions SET date = date(date, '+N days');
UPDATE credit_card_transactions SET date = date(date, '+N days');
UPDATE cash_transactions SET date = date(date, '+N days');
UPDATE manual_investment_transactions SET date = date(date, '+N days');
UPDATE investment_balance_snapshots SET date = date(date, '+N days');
UPDATE investments SET created_date = date(created_date, '+N days') WHERE created_date IS NOT NULL;
UPDATE investments SET closed_date = date(closed_date, '+N days') WHERE closed_date IS NOT NULL;
UPDATE investments SET liquidity_date = date(liquidity_date, '+N days') WHERE liquidity_date IS NOT NULL;
UPDATE investments SET maturity_date = date(maturity_date, '+N days') WHERE maturity_date IS NOT NULL;
UPDATE scraping_history SET date = date(date, '+N days');
-- Budget rules: shift year/month pairs
```

Budget rules store year/month integers, so those need arithmetic shifting rather than date() functions.

### Deactivation Flow

Same as current test mode: switch AppConfig back, reset engine, clear caches. The demo_env directory persists (user edits during demo are ephemeral — next activation overwrites with fresh copy).

## Renaming: Test Mode → Demo Mode

### Backend

| File | Change |
|------|--------|
| `backend/config.py` | `_test_mode` → `_demo_mode`, `test_env/` → `demo_env/`, `test_data.db` → `demo_data.db` |
| `backend/routes/testing.py` | Endpoint paths: `toggle_test_mode` → `toggle_demo_mode`, `test_mode_status` → `demo_mode_status` |
| `backend/services/credentials_service.py` | `is_test_mode` → `is_demo_mode`, keyring namespace stays `-test` or changes to `-demo` |
| `backend/repositories/credentials_repository.py` | Keyring namespace reference |
| All files referencing `AppConfig().is_test_mode` | Update to `is_demo_mode` |

### Frontend

| File | Change |
|------|--------|
| `TestModeContext.tsx` → `DemoModeContext.tsx` | Rename context, props, hooks |
| `Header.tsx` | Label "Test Mode" → "Demo Mode" |
| `api.ts` | Endpoint paths updated |
| `App.tsx` | Provider import updated |

## Demo Data: The Cohen Family

### Profile

Dual-income Israeli family household. ~38K ILS monthly income, mortgage, kids, diverse financial activity.

### Accounts

| Type | Provider | Account Name |
|------|----------|-------------|
| Bank | Hapoalim | Main Account |
| Credit Card | Max | Family Card |
| Credit Card | Visa Cal | Online Shopping |
| Cash | — | Petty Cash |
| Investment | — | Stock Market Fund (open, variable rate) |
| Investment | — | Savings Plan (open, fixed rate) |
| Investment | — | Corporate Bond (closed) |

### Income Sources (monthly)

| Source | Amount (ILS) | Frequency |
|--------|-------------|-----------|
| Salary — Tech Company | 18,000 | Monthly |
| Salary — School District | 12,000 | Monthly |
| Freelance Work | 1,000-2,500 | 3-4 times/year |
| Mortgage Receipt | 450,000 | One-time (14 months ago) |

### Expense Categories & Ranges

| Category | Tags | Monthly Range (ILS) |
|----------|------|-------------------|
| Food | Groceries, Restaurants, Coffee, Delivery | 3,500-5,000 |
| Transport | Gas, Parking, Public Transit | 1,200-1,800 |
| Home | Mortgage Payment, Utilities, Cleaning, Insurance | 6,500-8,000 |
| Entertainment | Streaming, Cinema, Events, Games | 400-800 |
| Health | Pharmacy, Doctor, Gym, Dental | 300-600 |
| Kids | Daycare, Activities, Clothing, School | 2,000-3,500 |
| Shopping | Electronics, Clothing, Online, Gifts | 500-2,000 |
| Education | Courses, Books, Conferences | 200-500 |
| Liabilities | Mortgage | 3,800/month (negative = payment) |
| Investments | Stock Fund, Savings Plan | 2,000-4,000/month deposits |

### Transaction Distribution

~80-120 transactions/month, ~1,000-1,500 total over 14 months:

| Source | % of Transactions | Notes |
|--------|------------------|-------|
| Bank | ~25% | Salary credits, mortgage, direct debits, CC bill payments |
| Credit Card (Max) | ~40% | Day-to-day purchases |
| Credit Card (Visa Cal) | ~25% | Online, shopping, subscriptions |
| Cash | ~5% | Small market purchases |
| Manual Investments | ~5% | Monthly deposits, 1 withdrawal |

### Special Feature Showcases

| Feature | Demo Data |
|---------|-----------|
| **Untagged transactions** | 5-8 transactions with no category (descriptions like "SHUFERSAL", "UBER", "Netflix") |
| **Tagging rules** | 8-10 rules: contains "SHUFERSAL" → Food/Groceries, contains "UBER" → Transport/Rides, etc. |
| **Split transactions** | 3 examples: supermarket (Food+Home), vacation (Entertainment+Transport), online order (Shopping+Kids) |
| **Pending refunds** | 2: one linked to actual refund transaction, one still pending |
| **Project budget** | "Home Renovation" — 15 transactions across Materials, Labor, Furniture tags, 30K budget |
| **Monthly budgets** | Last 3 months with realistic category limits |
| **Investments** | Stock fund: 12 months snapshots showing growth. Savings plan: fixed-rate auto-calculated. Bond: closed with final withdrawal |
| **Balance snapshots** | 10-15 per open investment, showing realistic market movements |
| **Bank balance** | Prior wealth set so cumulative chart starts at realistic level (~50K) |
| **Cash balance** | Petty Cash envelope with ~500 ILS balance |
| **CC deduplication** | Bank-side CC bill payments match (approximately) itemized CC totals |
| **Prior wealth** | Bank + investment prior wealth for realistic net worth starting point |
| **Scraping history** | A few "successful" scrape records to populate the data sources page |
| **Credential accounts** | 4 test scraper accounts (existing test providers) |

### Investment Details

| Name | Type | Rate | Status | Snapshots |
|------|------|------|--------|-----------|
| Stock Market Fund | Mutual Fund | 8.5% variable | Open | 12 monthly, showing ~7-10% annual growth with variance |
| Savings Plan | Savings | 4.2% fixed | Open | Auto-calculated daily compounding |
| Corporate Bond | Bond | 3.8% fixed | Closed (6 months ago) | Final snapshot = 0, withdrawal transaction present |

### Budget Rules (last 3 months)

| Category | Monthly Limit (ILS) |
|----------|-------------------|
| Total Budget | 28,000 |
| Food | 5,000 |
| Transport | 1,800 |
| Home | 8,000 |
| Entertainment | 800 |
| Health | 600 |
| Kids | 3,500 |
| Shopping | 2,000 |

### Tagging Rules

| Rule Name | Condition | Category/Tag |
|-----------|-----------|-------------|
| Supermarket | description contains "SHUFERSAL" or "RAMI LEVY" | Food / Groceries |
| Rides | description contains "UBER" or "GETT" | Transport / Rides |
| Streaming | description contains "NETFLIX" or "SPOTIFY" | Entertainment / Streaming |
| Gas Station | description contains "PAZ" or "SONOL" or "DELEK" | Transport / Gas |
| Pharmacy | description contains "SUPER-PHARM" | Health / Pharmacy |
| Daycare | description contains "GAN" and amount < -1000 | Kids / Daycare |
| Gym | description contains "HOLMES PLACE" | Health / Gym |
| Online Shopping | description contains "AMAZON" or "ALIEXPRESS" | Shopping / Online |

## Seed Script Design

`scripts/generate_demo_data.py`:

1. Creates fresh SQLite DB at `backend/resources/demo_data.db`
2. Uses SQLAlchemy models to create schema
3. Generates transactions with realistic patterns:
   - Recurring (salary, mortgage, subscriptions) — same day each month
   - Regular (groceries, gas) — 2-4x/month with amount variance
   - Sporadic (restaurants, shopping, events) — random frequency and amounts
4. Ensures CC deduplication is correct (bank CC bills ≈ sum of CC transactions per month)
5. Creates all supporting data (budgets, rules, investments, etc.)
6. Stores reference date as module constant

## Out of Scope

- No actual scraping capability in demo mode (test scrapers generate random data if triggered)
- No real credential validation
- Demo data is English-only (Hebrew descriptions could be added later)
- No automated demo data refresh in CI — manual `python scripts/generate_demo_data.py` when needed
