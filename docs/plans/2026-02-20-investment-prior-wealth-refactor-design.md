# Investment Prior Wealth Refactor — Design

**Date:** 2026-02-20
**Branch:** fullstack-refactor

## Problem

Prior wealth is handled inconsistently between bank accounts and investments:

- **Banks** → `BankBalance` table stores an explicit `prior_wealth_amount` per account. After each scrape, `BankBalanceService.recalculate_for_account()` updates the balance field while keeping `prior_wealth_amount` fixed. `TransactionsService._build_bank_prior_wealth_rows()` injects synthetic prior-wealth rows into the analysis transaction stream.
- **Investments** → No `prior_wealth_amount` stored anywhere. Instead, `TransactionsService.sync_prior_wealth_offset()` creates a single portfolio-level transaction (`tag=PRIOR_WEALTH_TAG`, positive amount = sum of all deposits) in the `manual_investment_transactions` table each time a transaction is created or deleted.

The result: bank prior wealth is a first-class DB field per account; investment prior wealth is a synthetic transaction at portfolio level derived from `sync_prior_wealth_offset`.

## Goal

Give each `Investment` record its own `prior_wealth_amount` column, calculated from its transactions, and updated automatically whenever a `ManualInvestmentTransaction` is created or deleted — mirroring how `BankBalance.prior_wealth_amount` works for scraped accounts.

## Approach

**Add `prior_wealth_amount` to the `Investment` model** (Approach A). No new table needed.

## Design

### 1. Data Model

Add to `backend/models/investment.py`:
```python
prior_wealth_amount = Column(Float, nullable=False, default=0.0)
```

**Migration** (startup seeding, matching project convention from commit `c6951d9`):
1. `ALTER TABLE investments ADD COLUMN prior_wealth_amount REAL NOT NULL DEFAULT 0.0` (idempotent — skip if column exists)
2. For each investment, compute `prior_wealth_amount = -(sum of all its ManualInvestmentTransactions)` and write it
3. Delete the existing portfolio-level prior wealth offset transactions from `manual_investment_transactions` (rows where `account_name = PRIOR_WEALTH_TAG` and `provider = "MANUAL"`)

### 2. Repository Layer

**`InvestmentsRepository`** — new method:
```python
def update_prior_wealth(self, investment_id: int, amount: float) -> None
```

### 3. Service Layer

**`InvestmentsService`** — two new methods:

```python
def recalculate_prior_wealth(self, investment_id: int) -> None:
    """
    Fetch all transactions for the investment, compute -(sum), store on the Investment record.
    Investment equivalent of BankBalanceService.recalculate_for_account().
    Called after any ManualInvestmentTransaction create/delete.
    """

def get_total_prior_wealth(self) -> float:
    """Sum Investment.prior_wealth_amount across all non-closed investments."""
```

**`TransactionsService.sync_prior_wealth_offset`** — remove the `manual_investments` branch. The method will only handle `cash` going forward.

**Circular dependency resolution**: `InvestmentsService` already imports `TransactionsService`. Rather than calling `InvestmentsService` from `TransactionsService` (circular), the **routes** call `InvestmentsService.recalculate_prior_wealth(investment_id)` after any investment transaction change — mirroring how `ScrapingService` calls `BankBalanceService.recalculate_for_account()` after a scrape.

### 4. Analysis Layer

**`TransactionsService`** — new private method:
```python
def _build_investment_prior_wealth_rows(self) -> pd.DataFrame
```
Mirrors `_build_bank_prior_wealth_rows()`. Reads all `Investment` records, emits one synthetic row per investment:
- `category = OTHER_INCOME`
- `tag = PRIOR_WEALTH_TAG`
- `amount = investment.prior_wealth_amount`
- `source = "investments"`

These rows are appended in `get_table()` alongside bank prior wealth rows.

**`AnalysisService`** — new method:
```python
def _get_investment_prior_wealth_total(self) -> float
```
Reads `Investment.prior_wealth_amount` directly via `InvestmentsRepository` for any analysis that needs the total without going through the transaction stream.

**Sankey (`get_sankey_data`)** — no changes. The `txn_prior_wealth` accumulator already picks up anything tagged `PRIOR_WEALTH_TAG` in the transaction stream; investment synthetic rows flow through naturally.

**`get_net_worth_over_time`** — no changes. Still calls `investments_service.get_total_value_at_date()` for investment value (calculated from transactions); prior wealth is tracked separately.

### 5. Testing

**Update:**
- `tests/backend/conftest.py` — `seed_investments` fixture: set `prior_wealth_amount` on seeded `Investment` records matching computed value from seeded transactions
- `test_transactions_service.py` — update `sync_prior_wealth_offset` tests to confirm `manual_investments` is no longer handled
- Route tests — investment transaction tests that previously asserted a prior wealth offset transaction exists in the table need updating

**Add:**
- `test_recalculate_prior_wealth_updates_investment_field` — create txn, assert `Investment.prior_wealth_amount` updated
- `test_get_total_prior_wealth` — multiple investments, assert sum correct
- `test_investment_prior_wealth_rows_in_get_table` — synthetic rows appear in `TransactionsService.get_table()` output with correct fields
- `test_sankey_includes_investment_prior_wealth` — end-to-end Sankey test covering investment prior wealth

## Files Touched

| File | Change |
|------|--------|
| `backend/models/investment.py` | +`prior_wealth_amount` column |
| `backend/repositories/investments_repository.py` | +`update_prior_wealth()` |
| `backend/services/investments_service.py` | +`recalculate_prior_wealth()`, +`get_total_prior_wealth()` |
| `backend/services/transactions_service.py` | Remove `manual_investments` from `sync_prior_wealth_offset`; +`_build_investment_prior_wealth_rows()`; call it in `get_table()` |
| `backend/services/analysis_service.py` | +`_get_investment_prior_wealth_total()` |
| `backend/routes/` (investment txn routes) | Call `recalculate_prior_wealth()` after create/delete |
| `backend/main.py` (or seeding module) | Migration: ALTER TABLE + seed `prior_wealth_amount` + cleanup old offset txns |
| `tests/backend/conftest.py` | Update `seed_investments` fixture |
| `tests/backend/unit/services/test_investments_service.py` | New tests |
| `tests/backend/unit/services/test_transactions_service.py` | Update sync tests |
| `tests/backend/routes/` | Update route tests |
