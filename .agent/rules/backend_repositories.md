---
trigger: glob
globs: backend/repositories/**/*.py, backend/database.py, backend/models/**/*.py
---

# Data Access Layer - Repository Pattern

## Purpose
Data access layer implementing the Repository Pattern. Repositories are the **ONLY** layer that interacts with the database or file system. They provide a clean abstraction over data persistence, returning pandas DataFrames or primitives with **zero business logic**.

## Core Principle: Separation of Concerns

### What Repositories DO:
✅ Execute database queries (SELECT, INSERT, UPDATE, DELETE)  
✅ Read/write YAML configuration files  
✅ Return pandas DataFrames for query results  
✅ Return primitives (bool, int, str) for simple operations  
✅ Handle table creation/schema management  
✅ Manage database transactions (commit/rollback)  

### What Repositories DO NOT DO:
❌ **No business logic** - no calculations, transformations, or decision-making  
❌ **No data validation** - services handle validation  
❌ **No filtering based on business rules** - only database-level filtering  
❌ **No calling other services** - only call other repositories if needed  
❌ **No UI logic** - repositories should not have any UI-specific logic

**Golden Rule:** If you need to think about "why" - it's business logic and belongs in services, not repositories.

## Architecture Overview

### Database Access
- **ORM:** SQLAlchemy ORM (using declarative models with `Base` and `TimestampMixin`)
- **Connection:** FastAPI dependency injection via `get_db()` context manager
- **Return Type:** Always `pd.DataFrame` for queries, primitives for boolean/counts
- **Transactions:** Managed via SQLAlchemy Session - use `db.commit()` after writes
- **Models:** All models inherit from `Base` and `TimestampMixin` for automatic timestamp management

### File Access (YAML)
- Used for **configuration data** that users edit via UI (categories, icons)
- Stored in `~/.finance-analysis/` (user data) or `backend/resources/` (defaults)
- Return type: Primitives (dict, list, bool) for YAML operations

### Repository Composition
Repositories can contain instances of other repositories:
```python
class TransactionsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.cc_repo = CreditCardRepository(db)
        self.bank_repo = BankRepository(db)
        self.cash_repo = CashRepository(db)
```

**Purpose:** Manage data from multiple sources/tables more easily. Each financial source (credit cards, banks, cash) has its own table, allowing easier data integration and merging.

## Repository Structure

### Standard Repository Pattern

```python
from sqlalchemy.orm import Session
from sqlalchemy import select, Column, Integer, String
import pandas as pd
from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables

# Define ExampleModel for the ORM example
class ExampleModel(Base, TimestampMixin):
    __tablename__ = Tables.EXAMPLE.value # Assuming Tables.EXAMPLE exists
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)

    def __repr__(self):
        return f"<ExampleModel(id={self.id}, name='{self.name}')>"

class ExampleRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def get_all(self) -> pd.DataFrame:
        """Read all records using ORM"""
        stmt = select(ExampleModel)
        result = self.db.execute(stmt)
        records = result.scalars().all()
        
        # Convert ORM objects to DataFrame
        if not records:
            return pd.DataFrame()
        
        data = [record.__dict__ for record in records]
        df = pd.DataFrame(data)
        # Remove SQLAlchemy internal state
        if '_sa_instance_state' in df.columns:
            df = df.drop('_sa_instance_state', axis=1)
        return df
    
    def add(self, name: str) -> None:
        """Insert new record using ORM"""
        new_record = ExampleModel(name=name)
        self.db.add(new_record)
        self.db.commit()  # CRITICAL: Always commit!
        self.db.refresh(new_record)  # Optional: refresh to get auto-generated fields
```

## ORM Models

### Base and TimestampMixin
All ORM models inherit from `Base` (SQLAlchemy declarative base) and `TimestampMixin`:

```python
from backend.models.base import Base, TimestampMixin
from sqlalchemy import Column, Integer, String

class MyModel(Base, TimestampMixin):
    __tablename__ = 'my_table'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
```

**TimestampMixin provides:**
- `created_at` - Automatically set on record creation
- `updated_at` - Automatically updated on record modification

**Benefits:**
- Automatic audit trail for all records
- No manual timestamp management required
- Consistent timestamp handling across all tables

### Existing ORM Models
Located in `backend/models/`:
- `transaction.py` - `BankTransaction`, `CreditCardTransaction`, `CashTransaction`, `ManualInvestmentTransaction`, `SplitTransaction`
- `budget.py` - `BudgetRule`
- `tagging.py` - `TaggingRule`
- `investment.py` - `Investment`
- `scraping.py` - `ScrapingHistory`

## Key Components

### Table Schema Management

#### ORM-Based Schema
**Purpose:** Tables are automatically created from ORM model definitions.

**How it works:** 
- Models defined in `backend/models/` inherit from `Base`
- `Base.metadata.create_all(engine)` creates all tables on startup
- Called in `backend/main.py` during application initialization

**Example Model Definition:**
```python
from backend.models.base import Base, TimestampMixin
from sqlalchemy import Column, Integer, String, Float
from backend.naming_conventions import Tables

class BudgetRule(Base, TimestampMixin):
    __tablename__ = Tables.BUDGET_RULES.value
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    amount = Column(Float)
    category = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
```

**Important Notes:**
- Tables created automatically on first run
- Schema changes require database migrations (manual or via Alembic)
- All models automatically get `created_at` and `updated_at` via `TimestampMixin`
- Table names defined in `naming_conventions.py` for consistency

### Transaction Management

**Critical:** SQLAlchemy Session requires explicit `commit()` for changes to persist.

**Pattern:**
```python
# ✅ CORRECT - Explicit commit
new_record = MyModel(name="example")
self.db.add(new_record)
self.db.commit()  # Required!

# ❌ WRONG - Changes not persisted
new_record = MyModel(name="example")
self.db.add(new_record)
# Missing commit - data lost!
```

**Rollback on Error:**
```python
try:
    record = MyModel(name="example")
    self.db.add(record)
    self.db.commit()
except Exception as e:
    self.db.rollback()
    raise
```

```python
def get_all(self) -> pd.DataFrame:
    """Read all records using ORM and return as DataFrame"""
    stmt = select(ExampleModel)
    records = self.db.execute(stmt).scalars().all()
    
    if not records:
        return pd.DataFrame()
    
    # Convert ORM objects to DataFrame
    df = pd.DataFrame([r.__dict__ for r in records])
    
    # Remove SQLAlchemy internal state
    if '_sa_instance_state' in df.columns:
        df = df.drop(columns=['_sa_instance_state'])
        
    return df
```

#### YAML Operations → Primitives
```python
def load_categories(self) -> dict[str, list[str]]:
    with open(file_path, 'r') as file:
        return yaml.load(file, Loader=yaml.FullLoader)

def file_exists(self, path: str) -> bool:
    return os.path.exists(path)
```

#### Single Value → Primitive
```python
def count_transactions(self) -> int:
    with self.conn.session as s:
        result = s.execute(text("SELECT COUNT(*) FROM transactions"))
        return result.scalar()

def transaction_exists(self, id: int) -> bool:
    with self.conn.session as s:
        result = s.execute(text("SELECT COUNT(*) FROM transactions WHERE id = :id"), {'id': id})
        return result.scalar() > 0
```

## Existing Repositories

### 1. `TransactionsRepository`
**Tables:** `credit_card_transactions`, `bank_transactions`, `cash_transactions`, `manual_investment_transactions`

**Purpose:** CRUD operations for all transaction types across multiple sources.

**Composition:** Contains `CreditCardRepository`, `BankRepository`, `CashRepository`, `ManualInvestmentTransactionsRepository`

**Key Methods:**
- `add_scraped_transactions()` - Insert transactions from scraper
- `get_all_transactions()` - Retrieve all transactions across sources
- `update_transaction_category_tag()` - Update tagging
- `delete_transaction()` - Remove transaction

**Business Logic Boundary:** Returns raw transaction DataFrames. Services handle filtering by date, category, amount calculations, etc.

### 2. `TaggingRepository`
**Storage:** YAML files (`categories.yaml`, `categories_icons.yaml`)

**Purpose:** Manage category/tag definitions and icon mappings.

**Key Methods:**
- `load_categories_from_file()` → `dict[str, list[str]]`
- `save_categories_to_file()` → `None`
- `get_categories_icons()` → `dict[str, str]`
- `update_category_icon()` → `bool`

**Why YAML instead of DB:** 
- Categories are **configuration**, not transactional data
- User edits via UI need to be human-readable
- Easy to version control defaults
- Simple backup/restore

### 3. `TaggingRulesRepository`
**Table:** `tagging_rules`

**Purpose:** Store and retrieve automatic tagging rules (priority-based pattern matching).

**Key Methods:**
- `get_all_rules()` - Retrieve rules ordered by priority
- `create_rule()` - Add new tagging rule
- `update_rule()` - Modify existing rule
- `delete_rule()` - Remove rule
- `get_rule_by_id()` - Fetch specific rule

**Special Field:** `conditions` - JSON string (parsing handled by service layer)

### 4. `BudgetRepository`
**Table:** `budget_rules`

**Purpose:** Manage monthly and project budgets.

**Key Methods:**
- `add()` - Create budget rule
- `read_all()` - Get all budgets
- `update()` - Modify budget amount/category
- `delete()` - Remove budget

**Special Fields:** `month` and `year` - `NULL` for project budgets (unlimited timeframe)

### 5. `SplitTransactionsRepository`
**Table:** `split_transactions`

**Purpose:** Track transaction splits across multiple categories.

**Key Methods:**
- `get_splits_for_transaction()` - Get all splits for a transaction ID
- `add_split()` - Create new split
- `update_split()` - Modify split
- `delete_splits()` - Remove all splits for transaction

**Relationship:** Linked to transactions via `transaction_id` foreign key

### 6. `ScrapingHistoryRepository`
**Table:** `scraping_history`

**Purpose:** Track scraping attempts (success/failed/canceled) for audit and rate limiting.

**Key Methods:**
- `record_scraping_attempt()` - Log scraping result
- `get_last_scraping_date()` - Check when account was last scraped
- `can_scrape_today()` - Enforce daily limit

**Status Constants:** `SUCCESS`, `FAILED`, `CANCELED`

### 7. `InvestmentsRepository`
**Table:** `investments`

**Purpose:** Manage investment portfolio tracking.

**Key Methods:**
- `create_investment()` - Add new investment
- `get_all_investments()` - Retrieve portfolio
- `update_balance()` - Update current value
- `close_investment()` - Mark as closed

**Special Fields:** `current_balance`, `last_balance_update`, `is_closed`

### 8. `CredentialsRepository`
**Storage:** YAML file (`~/.finance-analysis/credentials.yaml`) + Windows Keyring

**Purpose:** Manage user credentials for financial providers.

**Key Methods:**
- `read_credentials()` - Load all credentials
- `read_default_credentials()` - Load template structure
- `save_credentials()` - Persist to YAML

**Security Note:** Passwords stored in Windows Keyring, NOT in YAML (service layer responsibility)

### 9. `ScrapingRepository`
**Purpose:** Helper repository for scraping-related queries.

**Key Methods:**
- `get_last_transaction_date()` - Determine scraping start date
- `get_account_numbers()` - List available accounts

## When to Use YAML vs. Database

### Use YAML Files When:
✅ Data is **configuration** (categories, icons, default settings)  
✅ Users edit via UI and benefit from human-readable format  
✅ Data is hierarchical (nested dicts/lists)  
✅ Volume is small (< 1000 entries)  
✅ Version control of defaults is important  

### Use Database When:
✅ Data is **transactional** (transactions, budgets, rules)  
✅ Need to query/filter/join data  
✅ Volume is large or grows over time  
✅ Need referential integrity (foreign keys)  
✅ Concurrent access required  

**Example Decision:**
- **Categories** → YAML (configuration, hierarchical, rarely changes)
- **Tagging Rules** → Database (queryable, filterable, grows over time)

## Common Patterns

### CRUD Operations

#### Create
```python
def add(self, name: str, amount: float) -> None:
    with self.conn.session as s:
        cmd = sa.text(f"""
            INSERT INTO {self.table} ({self.name_col}, {self.amount_col})
            VALUES (:{self.name_col}, :{self.amount_col})
        """)
        s.execute(cmd, {self.name_col: name, self.amount_col: amount})
        s.commit()
```

#### Read
```python
def get_by_id(self, id: int) -> pd.DataFrame:
    with self.conn.session as s:
        query = f"SELECT * FROM {self.table} WHERE {self.id_col} = :id"
        result = s.execute(text(query), {'id': id})
        df = pd.DataFrame(result.fetchall())
        if not df.empty:
            df.columns = result.keys()
        return df
```

#### Update
```python
def update(self, id: int, **fields) -> None:
    if not fields:
        return
    
    set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
    fields['id'] = id
    
    with self.conn.session as s:
        cmd = sa.text(f"UPDATE {self.table} SET {set_clause} WHERE {self.id_col} = :id")
        result = s.execute(cmd, fields)
        s.commit()
        
        if result.rowcount == 0:
            raise ValueError(f"No record found with ID {id}")
```

#### Delete
```python
def delete(self, id: int) -> None:
    with self.conn.session as s:
        cmd = sa.text(f"DELETE FROM {self.table} WHERE {self.id_col} = :id")
        result = s.execute(cmd, {'id': id})
        s.commit()
        
        if result.rowcount == 0:
            raise ValueError(f"No record found with ID {id}")
```

### Parameterized Queries (SQL Injection Prevention)

```python
# ✅ CORRECT - Parameterized
query = text("SELECT * FROM transactions WHERE amount > :amount")
result = s.execute(query, {'amount': 100})

# ❌ WRONG - SQL Injection risk
query = f"SELECT * FROM transactions WHERE amount > {amount}"
result = s.execute(text(query))
```

### DataFrame Column Mapping

```python
# Always map column names to DataFrame
result = s.execute(text(query))
df = pd.DataFrame(result.fetchall())
if not df.empty:
    df.columns = result.keys()  # Essential!
return df
```

### Conditional Queries

```python
def get_filtered(self, category: str = None, min_amount: float = None) -> pd.DataFrame:
    where_clauses = []
    params = {}
    
    if category:
        where_clauses.append("category = :category")
        params['category'] = category
    
    if min_amount is not None:
        where_clauses.append("amount >= :min_amount")
        params['min_amount'] = min_amount
    
    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    with self.conn.session as s:
        query = f"SELECT * FROM {self.table}{where_clause}"
        result = s.execute(text(query), params)
        df = pd.DataFrame(result.fetchall())
        if not df.empty:
            df.columns = result.keys()
        return df
```

## Adding a New Repository

### Step 1: Define Table in `naming_conventions.py`
```python
class Tables(Enum):
    NEW_TABLE = 'new_table'

class NewTableFields(Enum):
    ID = 'id'
    NAME = 'name'
    AMOUNT = 'amount'
```

### Step 2: Create Repository Class
```python
class NewRepository:
    table = Tables.NEW_TABLE.value
    id_col = NewTableFields.ID.value
    
    def __init__(self, conn: SQLConnection):
        self.conn = conn
        self.assure_table_exists()
    
    def assure_table_exists(self):
        # Define schema
        pass
    
    # Implement CRUD methods
```

### Step 3: Use in Service Layer
```python
class NewService:
    def __init__(self):
        self.repo = NewRepository(get_db_connection())
```

## Error Handling

### Database Errors
```python
try:
    with self.conn.session as s:
        s.execute(...)
        s.commit()
except sa.exc.IntegrityError as e:
    # Unique constraint violation, foreign key error, etc.
    raise ValueError(f"Database constraint violation: {e}")
except sa.exc.OperationalError as e:
    # Database locked, disk full, etc.
    raise RuntimeError(f"Database operation failed: {e}")
```

### File Errors
```python
try:
    with open(file_path, 'r') as f:
        data = yaml.load(f)
except FileNotFoundError:
    return {}  # Return empty default
except yaml.YAMLError as e:
    raise ValueError(f"Invalid YAML file: {e}")
```

## Best Practices

1. **Always commit after writes** - Necessary for changes to persist
2. **Use parameterized queries** - Prevent SQL injection
3. **Map DataFrame columns** - Ensure column names are set
4. **Return empty DataFrames, not None** - Easier for services to handle
5. **Keep methods focused** - One query per method
6. **No business logic** - Push calculations to service layer
7. **Use enums for column names** - Centralized in `naming_conventions.py`
8. **Handle empty results gracefully** - Check `df.empty` before accessing
9. **Document expected return types** - DataFrame structure, dict schema, etc.
10. **Use SQLAlchemy Core over raw SQL** - Easier DB portability

## Testing

### Unit Tests
- Mock `SQLConnection` and `session`
- Test CRUD operations return correct DataFrames
- Verify parameterized queries prevent injection
- Test error handling (constraints, missing records)

### Integration Tests
- Test against real SQLite database
- Verify table creation works
- Test transactions commit correctly
- Verify DataFrame structures match expectations

## Notes
- Connection pooling handled automatically by SQLAlchemy
- Schema migrations not supported - manual DB updates required for schema changes
- Prefer SQLAlchemy Core over ORM for simplicity and portability
- YAML files for configuration, database for transactional data
- Repository composition (nested repos) used for multi-source data management
- Always return pandas DataFrames for queries (except primitives for counts/booleans)
- Transactions must be explicitly committed - no auto-commit


