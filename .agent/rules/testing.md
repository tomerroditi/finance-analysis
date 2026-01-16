# Testing Standards

Rules and best practices for writing tests in the Finance Analysis Dashboard project.

## Directory Structure
New tests should be added to the appropriate directory under `tests/`:
- `tests/backend/unit/`: Unit tests for individual classes and functions.
- `tests/backend/integration/`: Tests for multiple components interacting (e.g., Service + Repository).
- `tests/backend/routes/`: Tests for FastAPI endpoints.
- `tests/frontend/`: (Planned) Vitest for frontend components.

## General Principles
- **Framework**: Use `pytest`.
- **Grouping**: Always use test classes to group tests related to the same class or feature.
  ```python
  class TestClassName:
      def test_method(self):
          ...
  ```
- **Fixtures**: Use fixtures (shared in `tests/conftest.py` or defined locally) to reduce code repetition.
- **High Coverage, High Quality**: Aim for high coverage, but avoid "garbage tests" that increase coverage without providing real value. Every test should have a clear purpose and assertion.
- **Docstrings**: Every test class and test function MUST have a descriptive docstring.
- **Assertions**: Use clear and descriptive assertions.
- **Mocks**: Use `pytest-mock` or `unittest.mock` to isolate units under test, especially when dealing with external services or complex dependencies.

## Synchronization
> [!IMPORTANT]
> When making changes to the test structure, naming conventions, or global fixtures, you MUST update this rule file to reflect the changes.
