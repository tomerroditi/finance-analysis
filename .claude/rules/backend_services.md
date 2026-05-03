---
paths:
  - "backend/services/**/*.py"
---

# Services Layer - Business Logic

Services contain **ALL business logic**. They orchestrate repositories, handle calculations, transformations, validations, and decision-making.

## What Services DO / DON'T Do

| DO | DON'T |
|-------|----------|
| Business calculations (totals, aggregations) | Direct database access (use repos) |
| Data transformations, filtering, merging | UI rendering |
| Complex validations with business context | Direct file I/O (use repos) |
| Orchestrate repositories/services | Circular service dependencies |
| Error handling with business context | |
| Password retrieval from Keyring | |

**Golden Rule:** If it's about "what the data means" or "what to do with it" - it's business logic.

## Architecture

### Service Composition
```python
# Basic Service - Only repositories
class TransactionsService:
    def __init__(self, db: Session):
        self.transactions_repo = TransactionsRepository(db)

# Complex Service - Uses other services
class BudgetService:
    def __init__(self, db: Session):
        self.budget_repo = BudgetRepository(db)
        self.transactions_service = TransactionsService(db)
```

**Dependency Direction:** `Complex Services -> Basic Services -> Repositories -> Database`

### Return Types
- `pd.DataFrame` for tabular data
- Primitives (`int`, `float`, `bool`) for calculations
- `dict`/`list` for structured data

## Existing Services

| Service | Purpose |
|---------|---------|
| `TransactionsService` | CRUD for all transaction types, merging sources, date/category filtering |
| `TaggingService` | Category/tag config (YAML), add/delete/rename categories |
| `TaggingRulesService` | Auto-tagging rules (priority-based, JSON conditions) |
| `BudgetService` | Monthly/project budgets, budget vs actual comparison |
| `ScrapingService` | Orchestrate scraping, keyring passwords, 2FA coordination |
| `CredentialsService` | Read/write credentials YAML + Keyring interactions |
| `AnalysisService` | Dashboard aggregations, monthly summaries, trends |
| `InvestmentsService` | Portfolio tracking, balance snapshots, profit/loss, fixed-rate calculation, close/reopen lifecycle |

## Key Business Rules

### Transaction Amounts
- **Negative = expense**, **Positive = income**
- Filter with `amount < 0` for expenses only

### Tagging Rules Evaluation
1. Rules sorted by **priority DESC** (highest first)
2. First matching rule wins
3. Operators: `contains`, `equals`, `starts_with`, `gt`, `lt`, `between`
4. Fields: `description`, `amount`, `provider`, `account_name`, `service`

### Split Transactions
- Original transaction unchanged in main table
- Splits stored in `split_transactions` table
- Merge splits with originals in service layer for analysis

### Budget Storage
- Tags stored as semicolon-separated string: `"tag1;tag2;tag3"`
- Project budgets: `month` and `year` are `NULL`

### Non-Expense Categories
Exclude from expense analysis: `Ignore`, `Salary`, `Other Income`, `Investments`, `Liabilities`

## Common Patterns

### Data Merging (Transactions + Splits)
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

### Empty DataFrame Schema Guarantee (CRITICAL)

A service that returns a `pd.DataFrame` MUST return one with the canonical
columns even when there is zero data. A column-less empty DataFrame crashes
every consumer that does `df["col"]`.

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

**Required tests:** every analytic method must have a regression test that
runs against an empty DB and asserts no exception. The pattern that broke
production: a brand-new install or a logged-out demo DB has zero rows, the
DataFrame has zero columns, and `KeyError: 'category'` 500s the dashboard.

### Validation Pattern
```python
def validate_input(self, value: float) -> tuple[bool, str]:
    if value <= 0:
        return False, "Value must be positive"
    if self.exceeds_limit(value):
        return False, "Exceeds allowed limit"
    return True, ""
```

### Error Handling
```python
def update_budget(self, id: int, amount: float):
    try:
        self.budget_repo.update(id, amount=amount)
    except ValueError as e:
        raise ValueError(f"Failed to update budget: {e}")
```

## Adding a New Service

1. **Determine type:** Basic (repos only) or Complex (uses other services)
2. **Check dependencies:** Ensure no circular dependencies
3. **Create class:** Accept `db: Session`, instantiate repos/services
4. **Add validation:** Complex business rules in service
5. **Handle errors:** Catch repo errors, add business context

## Best Practices

1. **Keep business logic here** - not in repos or routes
2. **Linear dependencies** - no circular service imports
3. **Validate with context** - Simple in routes, complex in services
4. **Handle negative amounts** - Negative = expense convention
5. **Use dependency injection** - Accept `db` for testing
