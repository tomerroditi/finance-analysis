# API Design Patterns

FastAPI-specific patterns and conventions for this project.

## Route Structure

### File Organization

Each feature gets its own route file in `backend/routes/`:

```
backend/routes/
├── __init__.py          # Exports all routers
├── transactions.py      # Transaction CRUD
├── budget.py            # Budget management
├── tagging.py           # Categories and tags
├── analytics.py         # Dashboard analytics
└── ...
```

### Router Registration

Register routers in `backend/main.py`:

```python
from backend.routes import transactions, budget, tagging

app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(budget.router, prefix="/api/budget", tags=["Budget"])
app.include_router(tagging.router, prefix="/api/tagging", tags=["Tagging"])
```

## Pydantic Model Patterns

### Naming Conventions

| Pattern | Use Case | Example |
|---------|----------|---------|
| `{Entity}Create` | POST request body | `TransactionCreate` |
| `{Entity}Update` | PUT/PATCH request body | `TransactionUpdate` |
| `{Entity}Response` | Response model | `TransactionResponse` |
| `{Entity}Filter` | Query parameters | `TransactionFilter` |

### Create vs Update Models

```python
from pydantic import BaseModel
from typing import Optional
from datetime import date


class BudgetCreate(BaseModel):
    """Required fields for creation."""
    name: str
    amount: float
    category: str


class BudgetUpdate(BaseModel):
    """All fields optional for partial updates."""
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None


class BudgetResponse(BaseModel):
    """Full model for responses."""
    id: int
    name: str
    amount: float
    category: str
    created_at: date

    class Config:
        from_attributes = True  # Enable ORM mode
```

### Nested Models

```python
class SplitItem(BaseModel):
    amount: float
    category: str
    tag: str


class SplitRequest(BaseModel):
    source: str
    splits: list[SplitItem]
```

## Dependency Injection

### Database Session

Always use the `get_database` dependency:

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from backend.dependencies import get_database


@router.get("/")
async def get_items(db: Session = Depends(get_database)):
    # db is automatically provided and cleaned up
    pass
```

### Creating Services in Routes

Instantiate services inside route handlers (not as module-level):

```python
# ✅ Correct - create service with injected db
@router.get("/")
async def get_items(db: Session = Depends(get_database)):
    service = MyService(db)
    return service.get_all()


# ❌ Wrong - module-level service has no db session
service = MyService()  # No db!

@router.get("/")
async def get_items():
    return service.get_all()  # Will fail
```

## Query Parameters

### Optional Filters

```python
from typing import Optional
from fastapi import Query


@router.get("/")
async def get_transactions(
    service: Optional[str] = Query(None, description="Filter by service type"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_database)
):
    pass
```

### Required Query Params

```python
@router.delete("/{id}")
async def delete_item(
    id: int,
    source: str = Query(..., description="Source is required"),  # ... means required
    db: Session = Depends(get_database)
):
    pass
```

## Path Parameters

### Type Validation

FastAPI automatically validates path parameter types:

```python
@router.get("/{item_id}")
async def get_item(item_id: int):  # Automatically validates as int
    pass


@router.get("/{unique_id}")
async def get_item(unique_id: str):  # String path param
    pass
```

## Response Patterns

### Return Dictionaries

For simple responses:

```python
@router.post("/")
async def create_item(data: ItemCreate, db: Session = Depends(get_database)):
    service = MyService(db)
    service.create(data)
    return {"status": "success"}
```

### Return DataFrame as Records

For list responses:

```python
@router.get("/")
async def get_all(db: Session = Depends(get_database)):
    service = MyService(db)
    df = service.get_all()
    return df.to_dict(orient="records")
```

### Return Pydantic Models

For typed responses:

```python
@router.get("/{id}", response_model=ItemResponse)
async def get_item(id: int, db: Session = Depends(get_database)):
    service = MyService(db)
    return service.get_by_id(id)  # ORM object auto-converted
```

## Status Codes

### Implicit Status Codes

FastAPI uses sensible defaults:
- `GET` → 200 OK
- `POST` → 200 OK (can override to 201)
- `DELETE` → 200 OK (can override to 204)

### Explicit Status Codes

```python
from fastapi import status


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate):
    pass


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(id: int):
    pass  # Return nothing for 204
```

## Error Handling

### Don't Use HTTPException Directly

Use custom exceptions and global handlers:

```python
# ❌ Avoid - couples routes to HTTP details
from fastapi import HTTPException

@router.get("/{id}")
async def get_item(id: int):
    item = repo.get(id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


# ✅ Preferred - use domain exceptions
from backend.errors import EntityNotFoundException

@router.get("/{id}")
async def get_item(id: int, db: Session = Depends(get_database)):
    service = MyService(db)
    return service.get_by_id(id)  # Service raises EntityNotFoundException

# The global handler in main.py converts it to 404
```

## RESTful Conventions

### URL Structure

| Method | URL | Action |
|--------|-----|--------|
| GET | `/api/items` | List all |
| GET | `/api/items/{id}` | Get one |
| POST | `/api/items` | Create |
| PUT | `/api/items/{id}` | Full update |
| PATCH | `/api/items/{id}` | Partial update |
| DELETE | `/api/items/{id}` | Delete |

### Nested Resources

For related resources, use nested paths:

```python
# Transaction splits
@router.post("/{transaction_id}/split")
async def split_transaction(transaction_id: int, data: SplitRequest):
    pass


@router.delete("/{transaction_id}/split")
async def revert_split(transaction_id: int):
    pass
```

### Bulk Operations

Use action-based endpoints for bulk operations:

```python
@router.post("/bulk-tag")
async def bulk_tag_transactions(data: BulkTagUpdate):
    pass


@router.post("/bulk-delete")
async def bulk_delete(data: BulkDeleteRequest):
    pass
```

## Docstrings

Always add docstrings to routes - they appear in Swagger docs:

```python
@router.get("/")
async def get_transactions(
    service: Optional[str] = Query(None, description="Filter by service")
):
    """
    Get all transactions, optionally filtered by service.

    Returns a list of transaction records with all fields.
    """
    pass
```
