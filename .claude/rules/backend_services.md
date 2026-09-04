---
paths:
  - "backend/services/**/*.py"
---

# Services Layer — Business Logic

Services own **all** business logic: calculations, transformations, validation
with business context, orchestration. The layer boundary itself is in
`general.md`; this file is the stuff you can't infer from the directory.

## Shape

Constructor takes `db: Session` and builds its repos (and, for composite
services, other services). Dependency direction is strictly one-way —
composite services → basic services → repositories. No circular imports.

```python
class BudgetService:
    def __init__(self, db: Session):
        self.budget_repo = BudgetRepository(db)
        self.transactions_service = TransactionsService(db)
```

The three biggest domains are split into subpackages rather than one long
module — `analysis/` (`core`, `cashflow`, `forecast`, `net_worth`),
`budget/` (`core`, `monthly`, `project`, `yearly`), `investments/`
(`core`, `snapshots`, `valuation`, `insurance_sync`). New logic in those
domains goes in the matching module, not back into the flat `*_service.py`.

Return `pd.DataFrame` for tabular data, primitives for scalar calculations,
`dict`/`list` for structured payloads.

## Errors

Raise the `AppException` subclasses from `backend/errors.py` —
`EntityNotFoundException` (404), `EntityAlreadyExistsException` (409),
`ValidationException` (400), `BadRequestException` (400). Routes stay free of
try/except for domain errors, and the global handler maps them. Do **not**
re-raise as bare `ValueError` with a formatted message: it becomes an opaque
500, and the message can leak SQL or paths into the response body.

## Empty DataFrame Schema Guarantee (CRITICAL)

A service returning a `pd.DataFrame` MUST return one with the canonical columns
even when there is zero data. A column-less empty DataFrame crashes every
consumer that does `df["col"]`.

**Bad — crashes consumers on a fresh DB:**
```python
def get_data_for_analysis(self) -> pd.DataFrame:
    frames = [self.bank_repo.get_all(), self.cc_repo.get_all(), ...]
    return pd.concat(frames, ignore_index=True)  # empty if all sources empty
```

**Good — every consumer can do `df["category"]` safely:**
```python
ANALYSIS_COLUMNS = [
    "id", "date", "description", "amount", "category", "tag",
    "source", "provider", "account_name", "status", ...
]

def get_data_for_analysis(self) -> pd.DataFrame:
    frames = [self.bank_repo.get_all(), self.cc_repo.get_all(), ...]
    if all(f.empty for f in frames):
        return pd.DataFrame(columns=ANALYSIS_COLUMNS)
    return pd.concat(frames, ignore_index=True)
```

**Belt-and-braces — every analytic method also early-returns on empty:**
```python
def get_income_expenses_over_time(self, ...) -> list:
    df = self.transactions_service.get_data_for_analysis(...)
    if df.empty:
        return []
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    ...
```

**Required tests:** every analytic method needs a regression test that runs
against an empty DB and asserts no exception. The pattern that broke
production: a brand-new install or a logged-out demo DB has zero rows, the
DataFrame has zero columns, and `KeyError: 'category'` 500s the dashboard.

## Merging splits

A split transaction's original stays in the main table, so it must be dropped
before the splits are concatenated in — otherwise the amount is double-counted:

```python
def get_transactions_with_splits(self) -> pd.DataFrame:
    transactions = self.transactions_repo.get_all()
    splits = self.split_repo.get_all()
    if not splits.empty:
        split_ids = splits['transaction_id'].unique()
        transactions = transactions[~transactions['id'].isin(split_ids)]
        transactions = pd.concat([transactions, splits], ignore_index=True)
    return transactions
```

Full lifecycle in `split_transactions.md`.

## Conventions that live elsewhere

Transaction signs, non-expense categories, tagging-rule precedence, budget tag
storage, and the monthly/yearly/project discriminator (`period_type` — an
explicit column, **not** inferred from null `month`/`year`) are all in
`CLAUDE.md` → Key Conventions. Don't restate them here; they drifted last time.
