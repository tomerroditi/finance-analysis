---
globs: tests/**/*.py, pytest.ini, conftest.py
---

# Testing Standards

```
tests/
├── backend/
│   ├── unit/           # Individual classes/functions
│   │   ├── models/     # Tests for models
│   │   ├── services/   # Tests for services
│   │   ├── repositories/   # Tests for repositories
│   │   ├── routes/         # Tests for routes
│   │   └── scraper/        # Tests for scraper
│   ├── integration/    # Service + Repository interactions
│   └── routes/         # FastAPI endpoint tests
└── frontend/           # (Planned) Vitest for components
```

## Principles

| Rule | Details |
|------|---------|
| **Framework** | pytest |
| **Grouping** | Always use test classes to group related tests |
| **Fixtures** | Shared in `conftest.py`, reduce code repetition |
| **Docstrings** | Every test class and function MUST have one |
| **Mocks** | Use `pytest-mock` to isolate units |

## Test Class Pattern
```python
class TestClassName:
    """Tests for ClassName functionality."""

    def test_method_does_something(self):
        """Verify method returns expected result."""
        ...
```

## Route Testing with TestClient
```python
from fastapi.testclient import TestClient
from backend.main import app
from backend.dependencies import get_database
from unittest.mock import MagicMock

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200

def test_with_mock_db():
    mock_db = MagicMock()
    app.dependency_overrides[get_database] = lambda: mock_db
    response = client.delete("/api/investments/999999")
    assert response.status_code == 404
    app.dependency_overrides = {}
```

## Quality Guidelines
- **High coverage, high quality** - avoid "garbage tests" that don't add value
- Every test should have a clear purpose and assertion
- Use descriptive test names: `test_<method>_<scenario>_<expected>`
- Each test should be independent; clear `app.dependency_overrides` after each test
- Use mocks for unit/integration tests of routes to keep tests fast

## Running Tests
```bash
poetry run pytest                              # all tests
poetry run pytest tests/backend/unit/          # specific directory
poetry run pytest -k "test_budget"             # by keyword
```

> When changing test structure, naming conventions, or global fixtures, update this rule file.
