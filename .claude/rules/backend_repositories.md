---
paths:
  - "backend/repositories/**/*.py"
  - "backend/database.py"
  - "backend/models/**/*.py"
---

# Data Access Layer - Repository Pattern

Repositories are the **ONLY** layer that interacts with the database or file system. They return pandas DataFrames or primitives with **zero business logic**.

## What Repositories DO / DON'T Do

| DO | DON'T |
|-------|----------|
| Execute CRUD queries | Business logic (calculations, decisions) |
| Read/write YAML configs | Data validation (services handle this) |
| Return `pd.DataFrame` for queries | Filter based on business rules |
| Return primitives for counts/bools | Call services (only other repos) |
| Manage transactions (commit/rollback) | UI logic |

**Golden Rule:** If you need to think about "why" - it belongs in services.

## Architecture

- **ORM:** SQLAlchemy with `Base` + `TimestampMixin` (auto `created_at`/`updated_at`)
- **Connection:** FastAPI dependency injection via `get_db()` -> `Session`
- **Models:** Located in `backend/models/`, inherit from `Base` and `TimestampMixin`
- **YAML:** For configuration data (categories, icons) in `~/.finance-analysis/` or `backend/resources/`

## Standard Repository Pattern

```python
from sqlalchemy.orm import Session
from sqlalchemy import select
import pandas as pd
from backend.models.base import Base, TimestampMixin

class ExampleRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Query -> DataFrame conversion pattern"""
        records = self.db.execute(select(ExampleModel)).scalars().all()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame([r.__dict__ for r in records])
        return df.drop(columns=['_sa_instance_state'], errors='ignore')

    def add(self, name: str) -> None:
        """Insert pattern - ALWAYS commit!"""
        self.db.add(ExampleModel(name=name))
        self.db.commit()

    def update(self, id: int, **fields) -> None:
        record = self.db.get(ExampleModel, id)
        if not record:
            raise ValueError(f"No record with ID {id}")
        for k, v in fields.items():
            setattr(record, k, v)
        self.db.commit()

    def delete(self, id: int) -> None:
        record = self.db.get(ExampleModel, id)
        if not record:
            raise ValueError(f"No record with ID {id}")
        self.db.delete(record)
        self.db.commit()
```

## ORM Model Pattern

```python
from backend.models.base import Base, TimestampMixin
from sqlalchemy import Column, Integer, String
from backend.constants.tables import Tables

class MyModel(Base, TimestampMixin):
    __tablename__ = Tables.MY_TABLE.value
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
```

Tables auto-create on startup via `Base.metadata.create_all(engine)` in `backend/main.py`.

## Existing Repositories

| Repository | Storage | Purpose |
|------------|---------|---------|
| `TransactionsRepository` | DB (4 tables) | CRUD for bank/cc/cash/manual transactions. Composes sub-repos. |
| `TaggingRepository` | YAML files | Category/tag definitions, icon mappings |
| `TaggingRulesRepository` | DB | Auto-tagging rules (priority-based) |
| `BudgetRepository` | DB | Monthly & project budgets |
| `SplitTransactionsRepository` | DB | Transaction splits across categories |
| `ScrapingHistoryRepository` | DB | Scrape audit trail, rate limiting |
| `InvestmentsRepository` | DB | Investment portfolio tracking |
| `InvestmentSnapshotsRepository` | DB | Balance snapshot CRUD (upsert, get, delete by investment/source) |
| `CredentialsRepository` | YAML + Keyring | Provider credentials (passwords in Keyring) |

### Repository Composition
```python
class TransactionsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
```

## `unique_id` Is Per-Table — Never Use It Alone Across Tables

Every transaction table (`bank_transactions`, `credit_card_transactions`,
`cash_transactions`, `manual_investment_transactions`,
`insurance_transactions`) defines `unique_id` as its **own auto-increment
primary key**. The same integer exists in every table — bank #5 and
credit-card #5 are unrelated transactions. This has caused real bugs more
than once (most recently: a budget month override stored for a credit-card
transaction re-monthed the bank transaction sharing its integer, because the
lookup map was keyed by bare `unique_id` over the merged analysis frame).

**Rules:**

- `unique_id` only identifies a row **within one table**. The moment data
  from two or more transaction tables is merged (the analysis DataFrame,
  KPI inputs, budget views), bare `unique_id` is ambiguous.
- Any cross-table reference must carry the table alongside the id. Existing
  precedents to follow:
  - `pending_refunds`: `source_id` + `source_table`
  - `split_transactions`: `transaction_id` + `source`
  - `budget_month_overrides`: `source_id` + `source_table` (and the
    override map is keyed by `(source_table, source_id)`)
- When building a dict/map from one of those tables to apply over a merged
  DataFrame, key it by `(source_table, unique_id)` — never by `unique_id`
  alone. Same for joins, `Series.map`, `isin` filters, and caches.
- API payloads that point at a transaction must include both fields; the
  frontend sends `tx.source` as the table identifier (it holds the table
  name, e.g. `"bank_transactions"`).
- Frontend React keys follow the same logic: `` `${tx.source}_${tx.unique_id}` ``
  (see `frontend_pitfalls.md` → "Key Generation in Lists").

If you find yourself writing `df["unique_id"].map(...)` or
`WHERE unique_id = :id` without already knowing **which table** the id came
from, stop — that's the bug.

## YAML vs Database

| Use YAML | Use Database |
|----------|--------------|
| Configuration data | Transactional data |
| Hierarchical, rarely changes | Queryable, filterable |
| Small volume (<1000) | Grows over time |
| Human-editable | Referential integrity needed |

## Error Handling

```python
try:
    self.db.add(record)
    self.db.commit()
except sa.exc.IntegrityError:
    self.db.rollback()
    raise ValueError("Constraint violation")
```

## Best Practices

1. **Always commit after writes**
2. **Use ORM methods** - avoid raw SQL
3. **Return empty DataFrames, not None**
4. **Use enums** from `backend/constants/` for table/column names
5. **Handle empty results** - check `df.empty`
6. **Parameterize queries** - never string interpolate user input
