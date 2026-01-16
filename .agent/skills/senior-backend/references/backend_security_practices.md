# Security Practices

Backend security patterns specific to this project.

## Credential Management

### OS Keyring for Passwords

**NEVER** store passwords in code, config files, or YAML:

```python
import keyring

# ✅ Correct - use OS Keyring
password = keyring.get_password(service_name="provider_name", username="user123")

# ❌ Wrong - password in config
config = {
    "username": "user123",
    "password": "secret123"  # NEVER DO THIS!
}
```

### Credential Service Pattern

The `CredentialsService` handles password storage:

```python
from backend.services.credentials_service import CredentialsService

# Store password
service.set_password(provider="bank_name", username="user", password="secret")

# Retrieve password
password = service.get_password(provider="bank_name", username="user")

# Delete password
service.delete_password(provider="bank_name", username="user")
```

### YAML Stores Only Non-Sensitive Data

```yaml
# credentials.yaml - NO PASSWORDS HERE
banks:
  hapoalim:
    my_account:
      username: "user123"
      userCode: "12345"
      # password is in OS Keyring, NOT here
```

## Input Validation

### Pydantic for Request Validation

All request bodies must use Pydantic models:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional


class TransactionCreate(BaseModel):
    amount: float = Field(..., description="Transaction amount")
    description: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = None

    @validator('amount')
    def amount_must_be_nonzero(cls, v):
        if v == 0:
            raise ValueError('Amount cannot be zero')
        return v
```

### Query Parameter Validation

Use FastAPI's `Query` for validation:

```python
from fastapi import Query


@router.get("/")
async def get_items(
    limit: int = Query(default=100, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    category: str = Query(None, max_length=100)
):
    pass
```

### Path Parameter Validation

```python
from fastapi import Path


@router.get("/{item_id}")
async def get_item(
    item_id: int = Path(..., gt=0, description="Item ID must be positive")
):
    pass
```

## SQL Injection Prevention

### Use SQLAlchemy ORM

ORM queries are automatically parameterized:

```python
# ✅ Safe - ORM handles parameterization
from sqlalchemy import select

stmt = select(MyModel).where(MyModel.name == user_input)
result = db.execute(stmt).scalars().all()
```

### Parameterized Raw SQL

If you must use raw SQL:

```python
from sqlalchemy import text

# ✅ Safe - parameterized
result = db.execute(
    text("SELECT * FROM items WHERE name = :name"),
    {"name": user_input}
)

# ❌ DANGEROUS - SQL injection vulnerability!
result = db.execute(
    text(f"SELECT * FROM items WHERE name = '{user_input}'")
)
```

## CORS Configuration

CORS is configured in `backend/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**For production:**
- Limit `allow_origins` to actual frontend URLs
- Don't use `"*"` for methods/headers if not needed

## Exception Handling

### Don't Leak Internal Errors

Use custom exceptions with safe messages:

```python
from backend.errors import EntityNotFoundException, ValidationException

# ✅ Safe - controlled error message
raise EntityNotFoundException(f"Transaction {id} not found")

# ❌ Risky - may leak internal details
raise Exception(f"Database error: {db_error}")
```

### Global Exception Handlers

```python
# backend/main.py
@app.exception_handler(EntityNotFoundException)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundException):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message}
    )
```

## Logging

### Don't Log Sensitive Data

```python
import logging

logger = logging.getLogger(__name__)

# ✅ Safe logging
logger.info(f"User {username} logged in")

# ❌ NEVER log passwords or tokens!
logger.info(f"User {username} logged in with password {password}")
```

## 2FA Handling

The scraping service handles 2FA securely:

```python
class ScrapingService:
    def handle_2fa(self, provider: str, otp_code: str):
        """
        Pass 2FA code to scraper.
        OTP codes are short-lived and used immediately.
        """
        scraper = self._get_waiting_scraper(provider)
        scraper.set_otp_code(otp_code)
        # OTP is not stored or logged
```

## Environment Variables

For configuration that varies by environment:

```python
import os

# Database path
DB_PATH = os.environ.get('FAD_DB_PATH', os.path.join(USER_DIR, 'data.db'))

# Debug mode
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
```

**Never put secrets in environment variables** - use OS Keyring instead.

## File Path Security

### Validate User-Provided Paths

```python
from pathlib import Path

def safe_file_path(user_path: str, base_dir: Path) -> Path:
    """Ensure path is within allowed directory."""
    full_path = (base_dir / user_path).resolve()

    # Prevent directory traversal
    if not str(full_path).startswith(str(base_dir.resolve())):
        raise ValueError("Invalid path")

    return full_path
```

## Summary

| Area | Practice |
|------|----------|
| Passwords | Use OS Keyring, never in code/config |
| Input | Validate with Pydantic models |
| SQL | Use ORM or parameterized queries |
| Errors | Use custom exceptions, don't leak details |
| Logging | Never log passwords, tokens, or PII |
| CORS | Restrict origins in production |
