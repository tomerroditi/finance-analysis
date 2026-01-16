---
name: senior-backend
description: FastAPI backend development patterns for this finance analysis project. Covers Routes→Services→Repositories architecture, SQLAlchemy ORM, Pydantic validation, and exception handling. Use when creating API endpoints, implementing business logic, designing database models, or reviewing backend code.
---

# Senior Backend Development

Complete guide for backend development in this FastAPI + SQLAlchemy project.

## When to Use This Skill

- Creating new API endpoints
- Implementing business logic in services
- Designing database models and repositories
- Setting up exception handling
- Reviewing backend code for best practices

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic |
| Database | SQLite |
| Package Manager | Poetry |
| Dev Server | Uvicorn |

## Architecture Overview

```
Routes (FastAPI) → Services (Business Logic) → Repositories (Data Access) → Database
```

**Key Principles:**
- **Routes**: Handle HTTP concerns, use Pydantic for request/response validation
- **Services**: Orchestrate business logic, call repositories
- **Repositories**: ALL database operations, return DataFrames or primitives
- **Models**: SQLAlchemy ORM models + Pydantic schemas

## Quick Start

### Development Commands

```bash
# Start backend server
poetry run uvicorn backend.main:app --reload

# Run tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_app/test_my_feature.py

# Scaffold a new feature (generates route, service, repository, model)
python .agent/skills/senior-backend/scripts/scaffold_feature.py <feature_name>

# Dry run to see what would be created
python .agent/skills/senior-backend/scripts/scaffold_feature.py <feature_name> --dry-run
```

## Core Patterns

### 1. Creating a New Route

```python
# backend/routes/my_feature.py
"""
My Feature API routes.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.dependencies import get_database
from backend.services.my_feature_service import MyFeatureService

router = APIRouter()


# Pydantic models for request/response
class MyFeatureCreate(BaseModel):
    name: str
    amount: float
    category: Optional[str] = None


class MyFeatureResponse(BaseModel):
    id: int
    name: str
    amount: float
    category: Optional[str]

    class Config:
        from_attributes = True


@router.get("/")
async def get_all(db: Session = Depends(get_database)):
    """Get all items."""
    service = MyFeatureService(db)
    items = service.get_all()
    return items.to_dict(orient="records")


@router.post("/", response_model=MyFeatureResponse)
async def create(data: MyFeatureCreate, db: Session = Depends(get_database)):
    """Create a new item."""
    service = MyFeatureService(db)
    return service.create(data.name, data.amount, data.category)


@router.delete("/{item_id}")
async def delete(item_id: int, db: Session = Depends(get_database)):
    """Delete an item."""
    service = MyFeatureService(db)
    service.delete(item_id)
    return {"status": "success"}
```

**Register in main.py:**
```python
from backend.routes import my_feature
app.include_router(my_feature.router, prefix="/api/my-feature", tags=["MyFeature"])
```

### 2. Creating a Service

```python
# backend/services/my_feature_service.py
"""
My Feature business logic.
"""
import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.my_feature_repository import MyFeatureRepository
from backend.errors import EntityNotFoundException, ValidationException


class MyFeatureService:
    """Service for My Feature operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = MyFeatureRepository(db)

    def get_all(self) -> pd.DataFrame:
        """Get all items."""
        return self.repo.get_all()

    def create(self, name: str, amount: float, category: str = None):
        """Create a new item with business validation."""
        # Business validation
        if amount < 0:
            raise ValidationException("Amount cannot be negative")

        return self.repo.create(name=name, amount=amount, category=category)

    def delete(self, item_id: int) -> None:
        """Delete an item."""
        # Check exists first
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise EntityNotFoundException(f"Item {item_id} not found")

        self.repo.delete(item_id)
```

### 3. Creating a Repository

```python
# backend/repositories/my_feature_repository.py
"""
My Feature data access.
"""
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import MyFeatureModel


class MyFeatureRepository:
    """Repository for My Feature database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all items as DataFrame."""
        stmt = select(MyFeatureModel)
        records = self.db.execute(stmt).scalars().all()

        if not records:
            return pd.DataFrame()

        data = [r.__dict__ for r in records]
        df = pd.DataFrame(data)
        if '_sa_instance_state' in df.columns:
            df = df.drop(columns=['_sa_instance_state'])
        return df

    def get_by_id(self, item_id: int) -> MyFeatureModel | None:
        """Get a single item by ID."""
        return self.db.get(MyFeatureModel, item_id)

    def create(self, name: str, amount: float, category: str = None) -> MyFeatureModel:
        """Create a new item."""
        item = MyFeatureModel(name=name, amount=amount, category=category)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> None:
        """Delete an item."""
        item = self.db.get(MyFeatureModel, item_id)
        if item:
            self.db.delete(item)
            self.db.commit()
```

### 4. Creating an ORM Model

```python
# backend/models/my_feature.py
"""
My Feature database model.
"""
from sqlalchemy import Column, Integer, String, Float

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class MyFeatureModel(Base, TimestampMixin):
    """My Feature database model."""

    __tablename__ = Tables.MY_FEATURE.value  # Add to naming_conventions.py

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=True)

    def __repr__(self):
        return f"<MyFeatureModel(id={self.id}, name='{self.name}')>"
```

**Don't forget to:**
1. Add table name to `backend/naming_conventions.py`
2. Export model from `backend/models/__init__.py`

### 5. Exception Handling

Use the global exception handler pattern - don't catch exceptions in routes:

```python
# In services/repositories - raise custom exceptions
from backend.errors import EntityNotFoundException, ValidationException

# Raising exceptions
raise EntityNotFoundException(f"Budget {id} not found")
raise ValidationException("Invalid date range")

# Routes stay clean - no try/except needed
@router.get("/{id}")
async def get_item(id: int, db: Session = Depends(get_database)):
    service = MyService(db)
    return service.get_by_id(id)  # If not found, 404 returned automatically
```

**Available Exceptions:**
| Exception | HTTP Code | Use Case |
|-----------|-----------|----------|
| `EntityNotFoundException` | 404 | Record not found |
| `EntityAlreadyExistsException` | 409 | Duplicate record |
| `ValidationException` | 400 | Invalid input |

## Reference Documentation

For detailed patterns, see:
- [API Design Patterns](references/api_design_patterns.md) - Route structure, Pydantic models, REST conventions
- [Database Patterns](references/database_optimization_guide.md) - SQLAlchemy ORM, session management, queries
- [Security Practices](references/backend_security_practices.md) - Credentials, CORS, input validation

## Related Rules

The following rule files provide additional context:
- `.agent/rules/backend_services.md` - Service layer patterns
- `.agent/rules/backend_repositories.md` - Repository pattern details
- `.agent/rules/backend_resources.md` - Configuration and resources

## Related Workflows

- `/error-handling` - Backend exception handling guidelines
- `/testing-backend-routes` - Testing FastAPI routes

## Best Practices Summary

### Do ✅
- Use dependency injection for database sessions
- Keep routes thin - delegate to services
- Use Pydantic for all request/response validation
- Return DataFrames from repositories for tabular data
- Use `TimestampMixin` for automatic `created_at`/`updated_at`
- Raise custom exceptions, let global handlers respond

### Don't ❌
- Put business logic in routes
- Access database directly from routes
- Use try/except in routes for domain errors
- Forget to `db.commit()` after writes
- Store passwords in code or config files
