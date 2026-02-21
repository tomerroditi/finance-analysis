---
paths:
  - "tests/**/*.py"
  - "pytest.ini"
  - "conftest.py"
---

# Testing Standards

**523 tests, 80% backend coverage.** Run with `poetry run pytest --cov=backend`.

```
tests/
├── conftest.py                    # Root: db_engine + db_session (in-memory SQLite)
├── backend/
│   ├── conftest.py                # Seed fixtures (transactions, budgets, tagging rules, etc.)
│   ├── unit/
│   │   ├── test_config.py         # AppConfig singleton tests
│   │   ├── models/                # Per-model ORM tests (one file per model)
│   │   ├── services/              # Service tests (real DB, mock external deps)
│   │   ├── repositories/          # Repository tests (real DB, YAML uses tmp_path)
│   │   ├── utils/                 # Utility function tests
│   │   └── scraper/               # Scraper base class + 2FA tests
│   ├── integration/               # Cross-layer pipelines (tagging, budget, splits)
│   └── routes/
│       ├── conftest.py            # Route-specific: db_engine (StaticPool) + test_client
│       └── test_*_routes.py       # API endpoint tests (happy paths + error paths)
└── frontend/                      # (Planned) Vitest for components
```

## Principles

| Rule | Details |
|------|---------|
| **Framework** | pytest + pytest-cov |
| **Grouping** | Always use test classes to group related tests |
| **Fixtures** | Shared in `conftest.py`, reduce code repetition |
| **Docstrings** | Every test class and function MUST have one |
| **Naming** | `test_<method>_<scenario>_<expected>` |
| **Independence** | Each test is self-contained; no test depends on another |

## Test Class Pattern
```python
class TestClassName:
    """Tests for ClassName functionality."""

    def test_method_does_something(self):
        """Verify method returns expected result."""
        ...
```

## Fixture Architecture

### Root conftest (`tests/conftest.py`)
Provides `db_engine` and `db_session` using in-memory SQLite. All unit/integration tests share this.

### Seed fixtures (`tests/backend/conftest.py`)
Composable, function-scoped seed data — tests pick only what they need:

| Fixture | What it seeds |
|---------|---------------|
| `seed_base_transactions` | ~30 CC/bank/cash transactions across Jan-Mar 2024 |
| `seed_split_transactions` | Parent transactions + split children |
| `seed_prior_wealth_transactions` | Cash, manual investment, bank balances |
| `seed_untagged_transactions` | Transactions with no category/tag (for tagging rule tests) |
| `seed_project_transactions` | Wedding/Renovation project transactions + budget rules |
| `seed_budget_rules` | Monthly budget rules for Jan 2024 |
| `seed_tagging_rules` | Auto-tagging rules (Supermarket, Uber, Netflix) |
| `seed_investments` | Investment records + manual investment transactions |
| `sample_categories_yaml` | Categories-to-tags mapping dict (no DB) |
| `sample_credentials_yaml` | Fake credentials dict (no DB) |

### Route conftest (`tests/backend/routes/conftest.py`)
Overrides `db_engine` with **StaticPool** (required for TestClient sharing the same in-memory DB) and provides `test_client` fixture with dependency overrides.

## Unit Test Patterns

### Service tests (real DB)
Services are tested with a real in-memory DB session + seed fixtures. Mock only external dependencies (Keyring, file I/O).

```python
class TestBudgetServiceValidation:
    """Tests for budget validation edge cases."""

    def test_validate_null_category_rejected(self, db_session, seed_budget_rules):
        """Verify null category triggers validation failure."""
        service = BudgetService(db_session)
        valid, msg = service.validate_rule(category=None, tags=["Groceries"], ...)
        assert not valid
```

### Repository tests (YAML-based repos use tmp_path)
```python
class TestTaggingRepositoryLoad:
    """Tests for loading categories from YAML."""

    def test_load_categories(self, tmp_path):
        """Verify categories loaded from YAML file."""
        yaml_file = tmp_path / "categories.yaml"
        yaml_file.write_text("Food:\n  - Groceries\n")
        repo = TaggingRepository(categories_path=str(yaml_file))
        assert "Food" in repo.get_categories()
```

### Config tests (reset singleton between tests)
```python
@pytest.fixture(autouse=True)
def reset_config():
    """Reset AppConfig singleton state between tests."""
    AppConfig._test_mode = False
    AppConfig._base_user_dir = None
    yield
    AppConfig._test_mode = False
    AppConfig._base_user_dir = None
```

## Route Test Patterns

### Happy path (uses test_client + seed fixtures)
```python
class TestBudgetRoutes:
    """Tests for budget API endpoints."""

    def test_get_monthly_rules(self, test_client, seed_budget_rules):
        """Verify GET returns seeded budget rules."""
        response = test_client.get("/api/budget/rules/2024/1")
        assert response.status_code == 200
        assert len(response.json()) == 4
```

### Error path (mock service to trigger exceptions)
```python
from unittest.mock import patch, MagicMock

class TestTransactionsRoutesErrors:
    """Tests for transaction route error handling."""

    def test_create_transaction_value_error(self, test_client):
        """Verify ValueError returns 400."""
        with patch("backend.routes.transactions.TransactionsService") as mock:
            mock.return_value.create_transaction.side_effect = ValueError("bad input")
            response = test_client.post("/api/transactions/", json={...})
            assert response.status_code == 400
```

**Key:** Mock at the route module level (`backend.routes.transactions.TransactionsService`), not the service module.

## Quality Guidelines
- **High coverage, high quality** — avoid "garbage tests" that don't add value
- Every test should have a clear purpose and meaningful assertion
- Test both happy paths and error paths (400, 404, 500)
- Use seed fixtures for realistic data rather than minimal stubs
- For route error tests, use `unittest.mock.patch` to mock services at the route module level

## Running Tests
```bash
poetry run pytest                                      # all tests
poetry run pytest --cov=backend --cov-report=term-missing  # with coverage
poetry run pytest tests/backend/unit/                  # unit tests only
poetry run pytest tests/backend/routes/                # route tests only
poetry run pytest tests/backend/integration/           # integration tests only
poetry run pytest -k "test_budget"                     # by keyword
```

> When changing test structure, naming conventions, or global fixtures, update this rule file.
