---
trigger: glob
globs: tests/**/*.py, pytest.ini, conftest.py
---

# Testing Standards

## Directory Structure
```
tests/
├── backend/
│   ├── unit/           # Individual classes/functions
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

## Quality Guidelines
- **High coverage, high quality** - avoid "garbage tests" that don't add value
- Every test should have a clear purpose and assertion
- Use descriptive test names: `test_<method>_<scenario>_<expected>`

> [!IMPORTANT]
> When changing test structure, naming conventions, or global fixtures, update this rule file.
