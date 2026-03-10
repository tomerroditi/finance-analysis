# HaPhoenix Enhanced Scraper - Design Doc

## Context

The HaPhoenix scraper (`scraper/providers/insurances/hafenix.py`) currently has a working login flow with SMS 2FA and basic savings data extraction. This design enhances `fetch_data()` to scrape rich per-account detail from the Angular SPA at `my.fnx.co.il`.

## Data Available

HaPhoenix stores all API responses in `sessionStorage.appState`. The savings overview page populates `share.resSavings.savingList` with all accounts. Each account's detail page populates a separate key that gets **overwritten** when navigating to the next account.

### Per Account Type

**Pension** (key: `pensionPolicies.pensionPolicy`):
- Account name, pension type (makifa/mashlima), last updated date
- Investment tracks with yield (single track = 100% allocation; multi-track allocation TBD)
- Commission rates (from deposits, from savings/profits)
- Deposit history by year: employee/employer/compensation breakdown per deposit
- Insurance covers (disability, death) with costs from `accountTransactions`

**Keren Hishtalmut** (key: `gemelPolicies.hishtalmut`):
- Account name, policy number, last updated date
- Investment tracks with allocation %, yield, and sum per track
- Commission rates (from deposits, from savings/profits)
- Deposit history by year: total deposit amount per entry
- Liquidity date (parsed from `expectedPaymentsExcellence`)

## Scraper Flow

### 1. Account Discovery

Navigate to `/policies` (or use the already-loaded savingList from `/savings`). Extract all accounts from `appState.share.resSavings.savingList`, each with:
- `policyId`, `policyType` (pension/hishtalmut), `pensionType` (MAKIFA/MASHLIMA)
- `sum.value` (balance), `productDescription`, `tarNehunut` (balance date)

### 2. Per-Account Detail Scraping

For each account, sequentially:

1. Navigate to the detail page:
   - Pension: `/policies/pension/{policyId}/{pensionType.lower()}/info`
   - Hishtalmut: `/policies/hishtalmut/{encodeURI(policyId)}/info`
2. Wait for the relevant sessionStorage key to populate
3. Extract all data via `page.evaluate()` JS snippets
4. Move to next account (previous data gets overwritten)

### 3. Deposit Year Iteration

For each account's deposits section:
- Read the available years from the initial deposit data in sessionStorage
- For each year, trigger the year selector and wait for updated data
- Collect all deposit records across all available years

### 4. Data Assembly

Build `AccountResult` objects per account with:
- Deposit transactions (and insurance cost transactions for pension)
- Account metadata (investment tracks, commissions, covers, liquidity date)

## Storage Design

**Option chosen: Deposits as Transactions + new `insurance_accounts` metadata table.**

### Deposit Transactions

Map to the existing `Transaction` model in an `insurance_transactions` table:

| Transaction field | Pension mapping | Hishtalmut mapping |
|---|---|---|
| `date` | `depositDate` | `depositDate` |
| `description` | `"הפקדה - {employerName}"` | `"הפקדה"` |
| `original_amount` | `totalDeposit` (positive) | `totalDeposit` (positive) |
| `memo` | `"עובד: {employee} / מעסיק: {employer} / פיצויים: {compensation}"` | None |
| `identifier` | `"{policyId}_{date}_{amount}"` | Same pattern |

Pension insurance costs also become transactions:
- Negative amounts, description like `"עלות ביטוח - נכות"` / `"עלות ביטוח - מוות"`
- Identifier: `"{policyId}_{date}_insurance_{type}"`

### `insurance_accounts` Table (New)

One row per policy, upserted on each scrape:

| Column | Type | Description |
|---|---|---|
| `id` | int, PK | Auto-increment |
| `provider` | str | `"hafenix"` |
| `policy_id` | str, unique | The policyId |
| `policy_type` | str | `"pension"` / `"hishtalmut"` |
| `pension_type` | str, nullable | `"makifa"` / `"mashlima"` (pension only) |
| `account_name` | str | Policy name |
| `balance` | float | Current balance |
| `balance_date` | str | Last updated date |
| `investment_tracks` | JSON str | `[{name, yield_pct, allocation_pct, sum}]` |
| `commission_deposits_pct` | float, nullable | Commission from deposits |
| `commission_savings_pct` | float, nullable | Commission from savings/profits |
| `insurance_covers` | JSON str, nullable | `[{title, desc, sum}]` (pension only) |
| `liquidity_date` | str, nullable | Hishtalmut liquidity date |
| `updated_at` | datetime | Last scrape timestamp |

### Backend Adapter Integration

- New `_SERVICE_TO_TABLE` entry: `"insurances" -> "insurance_transactions"`
- Extend `AccountResult` with optional `metadata: dict | None` field
- Adapter checks for metadata and upserts `insurance_accounts` when present

## URL Patterns

- Savings overview: `https://my.fnx.co.il/savings`
- Policies list: `https://my.fnx.co.il/policies`
- Pension detail: `https://my.fnx.co.il/policies/pension/{policyId}/{pensionType}/info`
- Hishtalmut detail: `https://my.fnx.co.il/policies/hishtalmut/{encodeURI(policyId)}/info`

## SessionStorage Keys

- Account list: `appState.share.resSavings.savingList`
- Pension detail: `appState.pensionPolicies.pensionPolicy`
- Hishtalmut detail: `appState.gemelPolicies.hishtalmut`

## Open Items / TODOs

- Multi-track allocation % for pension (currently only single track observed, assumed 100%)
- Year iteration mechanism for deposits needs live testing (may require clicking a dropdown or API call)
- `show_browser=True` in `backend/scraper/adapter.py` needs to be reverted to `False`
