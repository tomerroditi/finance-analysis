# Database Patterns

SQLAlchemy ORM patterns and best practices for this project.

## ORM Model Structure

### Base Model Pattern

All models inherit from `Base` and `TimestampMixin`:

```python
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class MyModel(Base, TimestampMixin):
    """Description of the model."""

    __tablename__ = Tables.MY_TABLE.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<MyModel(id={self.id}, name='{self.name}')>"
```

**`TimestampMixin` provides:**
- `created_at` - Auto-set on creation
- `updated_at` - Auto-updated on modification

### Column Types

| Python Type | SQLAlchemy Column | Notes |
|-------------|-------------------|-------|
| `int` | `Column(Integer)` | |
| `float` | `Column(Float)` | |
| `str` | `Column(String)` | |
| `bool` | `Column(Boolean)` | |
| `datetime` | `Column(DateTime)` | |
| `date` | `Column(Date)` | |
| `Optional[str]` | `Column(String, nullable=True)` | |

### Nullable Fields

```python
# Required field
name = Column(String, nullable=False)

# Optional field (can be NULL)
category = Column(String, nullable=True)

# Default value
is_active = Column(Boolean, default=True, nullable=False)
```

## Naming Conventions

Define all table and field names in `backend/naming_conventions.py`:

```python
from enum import Enum


class Tables(Enum):
    """Database table names."""
    BANK_TRANSACTIONS = 'bank_transactions'
    CREDIT_CARD_TRANSACTIONS = 'credit_card_transactions'
    BUDGET_RULES = 'budget_rules'
    # Add new tables here


class BudgetRulesFields(Enum):
    """Budget rules table columns."""
    ID = 'id'
    NAME = 'name'
    AMOUNT = 'amount'
    CATEGORY = 'category'
```

## Session Management

### FastAPI Dependency Pattern

The session is managed via dependency injection:

```python
from backend.dependencies import get_database
from sqlalchemy.orm import Session
from fastapi import Depends


@router.get("/")
async def get_items(db: Session = Depends(get_database)):
    # db is a SQLAlchemy Session
    # Automatically closed after request
    pass
```

### Manual Context Manager

For background tasks or scripts:

```python
from backend.database import get_db_context

with get_db_context() as db:
    result = db.execute(text("SELECT * FROM items")).fetchall()
```

## Query Patterns

### Select All

```python
from sqlalchemy import select


def get_all(self) -> list[MyModel]:
    stmt = select(MyModel)
    return self.db.execute(stmt).scalars().all()
```

### Select with Filter

```python
def get_by_category(self, category: str) -> list[MyModel]:
    stmt = select(MyModel).where(MyModel.category == category)
    return self.db.execute(stmt).scalars().all()
```

### Select Single by ID

```python
def get_by_id(self, item_id: int) -> MyModel | None:
    return self.db.get(MyModel, item_id)
```

### Select with Multiple Conditions

```python
def get_filtered(self, category: str, min_amount: float) -> list[MyModel]:
    stmt = select(MyModel).where(
        MyModel.category == category,
        MyModel.amount >= min_amount
    )
    return self.db.execute(stmt).scalars().all()
```

### Select with Optional Filters

```python
def get_filtered(
    self,
    category: str | None = None,
    min_amount: float | None = None
) -> list[MyModel]:
    stmt = select(MyModel)

    if category is not None:
        stmt = stmt.where(MyModel.category == category)
    if min_amount is not None:
        stmt = stmt.where(MyModel.amount >= min_amount)

    return self.db.execute(stmt).scalars().all()
```

## CRUD Operations

### Create

```python
def create(self, name: str, amount: float) -> MyModel:
    item = MyModel(name=name, amount=amount)
    self.db.add(item)
    self.db.commit()  # CRITICAL: Always commit!
    self.db.refresh(item)  # Get auto-generated fields
    return item
```

### Update

```python
def update(self, item_id: int, **fields) -> MyModel | None:
    item = self.db.get(MyModel, item_id)
    if not item:
        return None

    for key, value in fields.items():
        if value is not None:
            setattr(item, key, value)

    self.db.commit()
    self.db.refresh(item)
    return item
```

### Delete

```python
def delete(self, item_id: int) -> bool:
    item = self.db.get(MyModel, item_id)
    if not item:
        return False

    self.db.delete(item)
    self.db.commit()
    return True
```

## DataFrame Conversion

Repositories typically return pandas DataFrames for tabular data:

```python
import pandas as pd
from sqlalchemy import select


def get_all_as_df(self) -> pd.DataFrame:
    """Get all records as a DataFrame."""
    stmt = select(MyModel)
    records = self.db.execute(stmt).scalars().all()

    if not records:
        return pd.DataFrame()

    # Convert ORM objects to dicts
    data = [r.__dict__ for r in records]
    df = pd.DataFrame(data)

    # Remove SQLAlchemy internal state
    if '_sa_instance_state' in df.columns:
        df = df.drop(columns=['_sa_instance_state'])

    return df
```

## Transaction Handling

### Explicit Commits

SQLAlchemy requires explicit commits:

```python
# ✅ Correct
item = MyModel(name="Test")
self.db.add(item)
self.db.commit()


# ❌ Wrong - changes not persisted!
item = MyModel(name="Test")
self.db.add(item)
# Missing commit!
```

### Rollback on Error

```python
def create_with_rollback(self, data: dict) -> MyModel:
    try:
        item = MyModel(**data)
        self.db.add(item)
        self.db.commit()
        return item
    except Exception:
        self.db.rollback()
        raise
```

### Multiple Operations

For multiple writes that should succeed or fail together:

```python
def transfer(self, from_id: int, to_id: int, amount: float):
    try:
        from_acc = self.db.get(Account, from_id)
        to_acc = self.db.get(Account, to_id)

        from_acc.balance -= amount
        to_acc.balance += amount

        self.db.commit()  # Both updates committed together
    except Exception:
        self.db.rollback()  # Both rolled back on failure
        raise
```

## Relationships

### One-to-Many

```python
class Parent(Base):
    __tablename__ = 'parents'
    id = Column(Integer, primary_key=True)
    children = relationship("Child", back_populates="parent")


class Child(Base):
    __tablename__ = 'children'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('parents.id'))
    parent = relationship("Parent", back_populates="children")
```

### Cascade Delete

```python
class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    splits = relationship(
        "SplitTransaction",
        back_populates="transaction",
        cascade="all, delete-orphan"  # Delete splits when transaction deleted
    )
```

## Performance Tips

### Avoid N+1 Queries

Use eager loading for relationships:

```python
from sqlalchemy.orm import selectinload

stmt = select(Parent).options(selectinload(Parent.children))
parents = self.db.execute(stmt).scalars().all()
```

### Query Only Needed Columns

```python
from sqlalchemy import select

# Select only specific columns
stmt = select(MyModel.id, MyModel.name)
results = self.db.execute(stmt).all()
```

### Batch Inserts

```python
def bulk_create(self, items: list[dict]):
    objects = [MyModel(**item) for item in items]
    self.db.add_all(objects)
    self.db.commit()
```

## Schema Management

Tables are created automatically from ORM models:

```python
# In backend/main.py (on startup)
from backend.models.base import Base
from backend.database import get_engine

engine = get_engine()
Base.metadata.create_all(bind=engine)
```

**Note:** Schema changes require manual migration or recreating tables. Consider using Alembic for complex migrations.

## Testing

### Use In-Memory SQLite

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.base import Base

# Create in-memory database for tests
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
TestSession = sessionmaker(bind=engine)

def test_create_item():
    db = TestSession()
    repo = MyRepository(db)
    item = repo.create(name="Test", amount=100)
    assert item.id is not None
    db.close()
```
