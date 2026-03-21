# Auto-create Investments from Scraped Keren Hishtalmut

## Problem

When insurance data is scraped from HaPhoenix, Keren Hishtalmut policies are stored as `InsuranceAccount` records with balance and metadata. However, to track them as investments (balance history, profit/loss, portfolio overview), users must manually create an `Investment` record. This should happen automatically.

## Scope

- **In scope:** Keren Hishtalmut policies only (`policy_type == "hishtalmut"`)
- **Out of scope:** Pension policies, transaction linking (deposits stay in `insurance_transactions` only)

## Design

### Linking Mechanism

A new nullable `insurance_policy_id` column on the `investments` table links an Investment to its source `InsuranceAccount.policy_id`. This enables:

- **First scrape:** No matching Investment found → create one
- **Subsequent scrapes:** Matching Investment found → update metadata + upsert balance snapshot

### Data Mapping

| InsuranceAccount | Investment | Notes |
|---|---|---|
| `policy_id` | `insurance_policy_id` | New column, lookup key |
| `account_name` | `name` | Human-readable policy name |
| `"Investments"` | `category` | Standard investment category constant |
| `"Keren Hishtalmut - {provider}"` | `tag` | Provider-qualified tag |
| `"hishtalmut"` | `type` | Investment type |
| `commission_deposits_pct` | `commission_deposit` | Fee on deposits |
| `commission_savings_pct` | `commission_management` | Fee on savings |
| `liquidity_date` | `liquidity_date` | Withdrawal eligibility date |
| _(not set)_ | `interest_rate_type` | `"variable"` (market-linked) |
| _(today)_ | `created_date` | Set on first creation only |

### Balance Snapshots

On each scrape where `balance` and `balance_date` are present on the insurance account:

- Upsert a balance snapshot with `source="scraped"` for that date
- If a `"scraped"` snapshot already exists for that exact date, update its balance value
- Never overwrite `"manual"` snapshots (same protection as fixed-rate calculated snapshots)

### Integration Point

`InsuranceScraperAdapter._post_save_hook()` — after upserting insurance account metadata (existing logic), iterate hishtalmut accounts and call `InvestmentsService.sync_from_insurance()`.

## Changes

### 1. Database Migration

Add `insurance_policy_id` column (nullable `String`) to `investments` table. Use Alembic or inline migration pattern consistent with existing codebase.

### 2. Investment Model (`backend/models/investment.py`)

Add:
```python
insurance_policy_id = Column(String, nullable=True, unique=True)
```

### 3. InvestmentsRepository (`backend/repositories/investments_repository.py`)

Add method:
```python
def get_by_insurance_policy_id(self, policy_id: str) -> pd.DataFrame:
    """Find investment linked to an insurance policy."""
```

### 4. InvestmentsService (`backend/services/investments_service.py`)

Add method:
```python
def sync_from_insurance(self, insurance_meta: dict) -> None:
    """Create or update an Investment from scraped insurance account metadata.

    Parameters
    ----------
    insurance_meta : dict
        Insurance account metadata dict with keys: policy_id, policy_type,
        provider, account_name, balance, balance_date, commission_deposits_pct,
        commission_savings_pct, liquidity_date.

    Only processes hishtalmut policies. Creates the Investment if not found
    by insurance_policy_id, otherwise updates metadata. Upserts a "scraped"
    balance snapshot if balance data is present.
    """
```

Logic:
1. Skip if `policy_type != "hishtalmut"`
2. Look up existing Investment by `insurance_policy_id`
3. If not found: create Investment with mapped fields
4. If found: update `name`, `commission_deposit`, `commission_management`, `liquidity_date`
5. If `balance` and `balance_date` present: upsert scraped balance snapshot (skip if manual snapshot exists for that date)

### 5. InsuranceScraperAdapter (`backend/scraper/adapter.py`)

Extend `_post_save_hook()`:
```python
# After existing metadata upsert loop
from backend.services.investments_service import InvestmentsService
inv_service = InvestmentsService(db)
for meta in accounts_to_upsert:
    inv_service.sync_from_insurance(meta)
```

### 6. Tests

- `test_sync_from_insurance_creates_investment`: First scrape creates Investment with correct fields
- `test_sync_from_insurance_updates_existing`: Subsequent scrape updates metadata
- `test_sync_from_insurance_creates_balance_snapshot`: Snapshot created with source="scraped"
- `test_sync_from_insurance_skips_pension`: Pension policies are ignored
- `test_sync_from_insurance_no_overwrite_manual_snapshot`: Manual snapshots preserved
- `test_sync_from_insurance_updates_existing_scraped_snapshot`: Re-scrape same date updates balance
