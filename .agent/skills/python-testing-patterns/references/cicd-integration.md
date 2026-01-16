# CI/CD Integration for Python Tests

Reference guide for integrating pytest with continuous integration systems.

## GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest pytest-cov

      - name: Run tests
        run: |
          pytest --cov=myapp --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## GitHub Actions with Poetry

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.12"

      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          version: latest
          virtualenvs-create: true
          virtualenvs-in-project: true

      - name: Load cached venv
        id: cached-poetry-dependencies
        uses: actions/cache@v3
        with:
          path: .venv
          key: venv-${{ runner.os }}-${{ hashFiles('**/poetry.lock') }}

      - name: Install dependencies
        if: steps.cached-poetry-dependencies.outputs.cache-hit != 'true'
        run: poetry install --no-interaction --no-root

      - name: Install project
        run: poetry install --no-interaction

      - name: Run tests
        run: poetry run pytest --cov=backend --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - test

test:
  stage: test
  image: python:3.12
  before_script:
    - pip install poetry
    - poetry install
  script:
    - poetry run pytest --cov=myapp --cov-report=xml
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

## Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: poetry run pytest
        language: system
        pass_filenames: false
        always_run: true
```

## Makefile Commands

```makefile
.PHONY: test test-cov test-fast

test:
	poetry run pytest

test-cov:
	poetry run pytest --cov=backend --cov-report=html

test-fast:
	poetry run pytest -x --ff

test-watch:
	poetry run ptw -- --last-failed
```

## Coverage Thresholds

```toml
# pyproject.toml
[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

## Tips

1. **Cache dependencies** to speed up CI runs
2. **Run tests in parallel** with `pytest-xdist` for large test suites
3. **Set coverage thresholds** to maintain code quality
4. **Use matrix testing** to test across Python versions
5. **Upload coverage reports** to Codecov or Coveralls for tracking
