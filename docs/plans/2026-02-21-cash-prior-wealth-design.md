# Cash Prior Wealth System Design

**Date:** 2026-02-21
**Status:** Approved
**Scope:** Support multiple cash envelopes with manual balance entry and automatic prior wealth calculation

## Overview

Currently, cash prior wealth is handled via manual "Prior Wealth" transactions in the cash transactions table. This design introduces a dedicated `cash_balances` table to mirror the `bank_balances` system, allowing users to:

1. Manually enter their current cash amount in multiple envelopes (e.g., "Wallet", "Home Safe")
2. Have the system automatically calculate `prior_wealth = balance - sum(all transactions)`
3. Automatically update current balance when new cash transactions are added/deleted
4. Prevent negative balances with validation

## Data Model

### CashBalance ORM Model

**File:** `backend/models/cash_balance.py`

```python
class CashBalance(Base, TimestampMixin):
    """ORM model for cash envelope balances and prior wealth."""

    __tablename__ = Tables.CASH_BALANCES.value  # "cash_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False, unique=True)
    balance = Column(Float, nullable=False)
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
    last_manual_update = Column(String, nullable=True)
```

**Columns:**
- `id`: Primary key
- `account_name`: Envelope identifier (e.g., "Wallet", "Home Safe"). Unique to prevent duplicate envelopes.
- `balance`: Current balance entered by user
- `prior_wealth_amount`: Fixed anchor point, only updates when user manually enters new balance
- `last_manual_update`: ISO date string of last manual balance entry
- `created_at`, `updated_at`: Inherited from `TimestampMixin`

**Key Differences from `BankBalance`:**
- No `provider` field (cash is local)
- No `last_scrape_update` (no scraping for cash)
- `account_name` is UNIQUE (one balance record per envelope)

## Service Layer

### CashBalanceService

**File:** `backend/services/cash_balance_service.py`

Methods:

#### `set_balance(account_name: str, balance: float) -> dict`
User manually enters current cash balance for an envelope.

**Steps:**
1. Validate `balance >= 0` (raise `ValidationException` if negative)
2. Fetch all cash transactions for this `account_name`
3. Calculate `prior_wealth = balance - sum(all transactions for account_name)`
4. Upsert `cash_balances` record with new balance and prior_wealth
5. Return updated record as dict

**Example:**
```
User enters: account_name="Wallet", balance=500
Existing transactions for "Wallet": [-50, -30, +10] = -70
prior_wealth = 500 - (-70) = 570
Stored: balance=500, prior_wealth_amount=570
```

#### `recalculate_current_balance(account_name: str) -> None`
Called after any cash transaction is added/updated/deleted. Recalculates current balance but keeps prior wealth fixed.

**Steps:**
1. Retrieve existing `prior_wealth_amount` for account
2. Fetch all cash transactions for account
3. Calculate `new_balance = prior_wealth + sum(current transactions)`
4. Update `balance` in db (prior_wealth stays unchanged)

**Example:**
```
prior_wealth=570, sum(txns)=-70
new_balance = 570 + (-70) = 500
```

#### `get_all_balances() -> list[dict]`
Returns all cash balance records.

#### `get_by_account_name(account_name: str) -> dict`
Returns a single balance record by account name.

#### `delete_for_account(account_name: str) -> None`
Deletes a cash balance record (e.g., when user closes an envelope).

#### `get_total_prior_wealth() -> float`
Sums `prior_wealth_amount` across all envelopes. Used in KPI calculations.

---

## API Routes

**File:** `backend/routes/cash_balances.py`

### GET `/api/cash-balances`
Get all cash balance records.

**Response:** `list[dict]`
```json
[
  {
    "id": 1,
    "account_name": "Wallet",
    "balance": 500.0,
    "prior_wealth_amount": 570.0,
    "last_manual_update": "2026-02-21"
  }
]
```

### POST `/api/cash-balances`
Set current balance for a cash envelope.

**Request:**
```json
{
  "account_name": "Wallet",
  "balance": 500.0
}
```

**Response:** Updated balance record (same structure as GET response)

**Errors:**
- `400 ValidationException`: Balance < 0, invalid account_name, or other validation failure

---

## Business Logic

### Prior Wealth Calculation Formula

When user enters a new balance:
```
prior_wealth = user_entered_balance - sum(all cash transactions for account_name)
```

When displaying current balance:
```
current_balance = prior_wealth + sum(all cash transactions for account_name to date)
```

### Recalculation Triggers

**Prior wealth is recalculated ONLY when:**
- User manually calls `set_balance()` endpoint

**Current balance is recalculated WHEN:**
- A cash transaction is created
- A cash transaction is updated
- A cash transaction is deleted

**Prior wealth stays FIXED between manual updates** (unlike investments where it recalculates after every transaction)

### Validation Rules

1. `balance >= 0` — No negative balances allowed
2. `account_name` non-empty string
3. `account_name` must be unique in `cash_balances` table

---

## Integration Points

### TransactionsService Integration

In `backend/services/transactions_service.py`, after any cash transaction modification:

```python
# In create_transaction()
if service == "cash":
    from backend.services.cash_balance_service import CashBalanceService
    CashBalanceService(db).recalculate_current_balance(account_name)

# In update_transaction()
if service == "cash":
    CashBalanceService(db).recalculate_current_balance(account_name)

# In delete_transaction()
if source == "cash_transactions":
    CashBalanceService(db).recalculate_current_balance(account_name)
```

### AnalysisService Integration (KPI Calculations)

In `backend/services/analysis_service.py`, update `get_overview()`:

```python
def get_overview():
    # Existing income/expense calculation
    total_income, total_expenses = self.get_income_and_expenses()

    # Add cash prior wealth (similar to bank and investment prior wealth)
    cash_service = CashBalanceService(db)
    cash_prior_wealth = cash_service.get_total_prior_wealth()
    total_income += cash_prior_wealth

    # ... rest of overview logic
```

---

## Frontend Integration

### New Components/Pages

- **Cash Balance List:** Display all cash envelopes with balances
- **Cash Balance Modal:** Form to add new envelope or update balance
- **New API Service Methods:**
  - `getCashBalances()` — GET /api/cash-balances
  - `setCashBalance(account_name, balance)` — POST /api/cash-balances

### Dashboard Integration

Add a "Cash" section to the dashboard overview showing total cash balance and breakdown by envelope.

---

## Error Handling

**ValidationException (400):**
- Balance is negative
- Account name is empty or invalid

**EntityNotFoundException (404):**
- Account name not found when querying

**EntityAlreadyExistsException (409):**
- Attempting to create duplicate account_name (if enforced)

---

## Testing Strategy

### Unit Tests
- `test_set_balance_calculates_prior_wealth_correctly`
- `test_recalculate_current_balance_keeps_prior_wealth_fixed`
- `test_set_balance_rejects_negative_balance`
- `test_set_balance_handles_no_transactions`
- `test_get_total_prior_wealth_sums_across_accounts`

### Integration Tests
- Test TransactionsService calls CashBalanceService on cash transaction changes
- Test AnalysisService includes cash prior wealth in overview

---

## Migration Notes

If users have existing "Prior Wealth" cash transactions:
1. These remain in the transaction table (no deletion needed)
2. When user first enters their current cash balance via the new endpoint, prior wealth is recalculated from transactions
3. The old manual "Prior Wealth" transactions can optionally be deleted (UX decision)

---

## Implementation Order

1. Add `Tables.CASH_BALANCES` constant
2. Create `CashBalance` ORM model
3. Create `CashBalanceRepository`
4. Create `CashBalanceService`
5. Create `/api/cash-balances` routes
6. Update `TransactionsService` to trigger `CashBalanceService.recalculate_current_balance()`
7. Update `AnalysisService.get_overview()` to include cash prior wealth
8. Update frontend with new cash balance UI
9. Add tests for all new functionality
10. Update KPI documentation in `.claude/rules/kpi_calculations.md`
