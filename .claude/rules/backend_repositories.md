---
globs: backend/repositories/**/*.py, backend/database.py, backend/models/**/*.py
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
from backend.naming_conventions import Tables

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
| `CredentialsRepository` | YAML + Keyring | Provider credentials (passwords in Keyring) |

### Repository Composition
```python
class TransactionsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
```

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
4. **Use enums** from `naming_conventions.py` for table/column names
5. **Handle empty results** - check `df.empty`
6. **Parameterize queries** - never string interpolate user input
