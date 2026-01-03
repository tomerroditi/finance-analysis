---
description: guidelines for backend exception handling and custom errors
---

# Backend Error Handling Workflow

This document outlines the standard procedure for handling errors in the FastAPI backend, ensuring consistency and clean route functions.

## 1. Define Custom Exceptions
All domain-specific exceptions should be defined in `backend/errors.py`. 
- Inherit from `AppException` (the base class).
- Use descriptive names (e.g., `InsufficientFundsException`).

```python
# backend/errors.py
class MyNewException(AppException):
    pass
```

## 2. Register Global Handlers
To automatically map a custom exception to an HTTP response, register it in `backend/main.py`.

```python
# backend/main.py
@app.exception_handler(MyNewException)
async def my_exception_handler(request: Request, exc: MyNewException):
    return JSONResponse(
        status_code=400, # Or appropriate code
        content={"detail": exc.message},
    )
```

## 3. Raise Exceptions in Repositories/Services
Instead of returning error codes or handling HTTP logic deep in the code, raise the custom exceptions directly when an error occurs.

```python
# backend/repositories/my_repo.py
def get_data(id):
    result = db.execute(...)
    if not result:
        raise EntityNotFoundException(f"ID {id} not found")
```

## 4. Keep Routes Clean
Route functions should **NOT** use `try...except` blocks for domain errors. They should assume success; if an exception is raised, the global handler will intercept it and return the correct response to the client.

```python
@router.get("/{id}")
async def get_something(id: int):
    # No try-except needed!
    return repo.get_data(id)
```

## Summary Table
| Exception | Suggested HTTP Code | Use Case |
|-----------|---------------------|----------|
| `EntityNotFoundException` | 404 | Record missing in DB |
| `ValidationException` | 400 | Invalid input data |
| `AppException` | 500 (default) | Base for all custom errors |
