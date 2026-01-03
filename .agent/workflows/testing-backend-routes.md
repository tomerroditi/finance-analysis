---
description: guidelines for testing FastAPI backend routes
---

# Backend Route Testing Workflow

This document describes how to write and run integration tests for the FastAPI backend routes.

## 1. Prerequisites
- `pytest`: The test runner.
- `httpx`: Used by FastAPI `TestClient` for making requests.

## 2. Setting Up TestClient
Use `fastapi.testclient.TestClient` to simulate requests to your API.

```python
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "Finance Analysis API"
```

## 3. Mocking Dependencies (Database)
Most routes depend on a database session via `get_database`. To avoid side effects, override this dependency in your tests.

```python
from backend.main import app
from backend.dependencies import get_database
from unittest.mock import MagicMock

def test_delete_investment_not_found():
    # 1. Create a mock DB session
    mock_db = MagicMock()
    
    # 2. Override the dependency
    app.dependency_overrides[get_database] = lambda: mock_db
    
    # 3. Simulate an error in the repository/service if needed
    # Note: With our global exception handlers, if the mock raises
    # EntityNotFoundException, the API will return 404 automatically.
    
    # 4. Make the request
    response = client.delete("/api/investments/999999")
    
    # 5. Assertions
    assert response.status_code == 404
    
    # 6. Clean up overrides
    app.dependency_overrides = {}
```

## 4. Testing Error Handling
With our global exception handling logic:
- Verify that custom exceptions (like `EntityNotFoundException`) correctly result in the desired HTTP status codes.
- Ensure the error message in the response `detail` field matches expectations.

## 5. Running Tests
Run all tests using poetry:

// turbo
```bash
poetry run pytest
```

To run a specific test file:
```bash
poetry run pytest tests/test_app/test_my_feature.py
```

## 6. Best Practices
- **Isolation**: Each test should be independent. Clear `app.dependency_overrides` after each test (consider using a pytest fixture).
- **Coverage**: Aim to test both successful operations and edge cases (invalid inputs, missing resources).
- **Mocks vs Real DB**: Use mocks for unit/integration tests of routes to keep tests fast and reliable.
