# Finance Analysis Dashboard

Personal finance tracking system for Israeli financial institutions. FastAPI backend + React 19 frontend.

## Commands

```bash
# Backend
poetry run uvicorn backend.main:app --reload          # Dev server (port 8000)
poetry run pytest                                      # All tests
poetry run pytest tests/backend/unit/                  # Unit tests only
poetry run pytest -k "test_budget"                     # By keyword

# Frontend (from frontend/)
npm run dev                                            # Dev server (port 5173)
npm run build                                          # Production build
npm run lint                                           # ESLint

# Both servers
python .claude/scripts/with_server.py -- <command>     # Start both, run command

# Scaffolding
python .claude/scripts/scaffold_feature.py <name>      # Generate route/service/repo boilerplate
```

## Environment Setup (New Clone / Worktree)

```bash
python3.12 -m venv .venv && source .venv/bin/activate && pip install poetry && poetry install --no-root
cd frontend && npm install
```

User data lives in `~/.finance-analysis/` (DB, credentials YAML, categories YAML). Auto-created on first run.

## Architecture

```
Routes (FastAPI) -> Services (Business Logic) -> Repositories (Data Access) -> SQLite
```

- **Backend:** `backend/` — FastAPI, SQLAlchemy ORM, Pandas DataFrames
- **Frontend:** `frontend/src/` — React 19, Vite, TanStack Query, Zustand, Tailwind CSS 4
- **Tests:** `tests/backend/unit/` — pytest with test classes, docstrings required
- **Rules:** `.claude/rules/` — detailed architecture docs (9 files covering services, repos, scraper, frontend, testing)

## Key Conventions

- **Transaction amounts:** negative = expense, positive = income or refund
- **Non-expense categories:** Ignore, Salary, Other Income, Investments, Liabilities
- **Service names:** frontend/API use plural (`banks`, `credit_cards`, `cash`, `manual_investments`)
- **Tags stored in budgets:** semicolon-separated (`"tag1;tag2;tag3"`)
- **Tagging rules:** priority DESC, first match wins
- **Split transactions:** original stays in main table, splits in `split_transactions`, merged in service layer

## Code Style

- Python: type hints, NumPy-style docstrings
- TypeScript: strict mode, no unused locals/parameters
- Tests: always use test classes, every test needs a docstring
- No business logic in routes or components — services handle all logic
- No direct DB access outside repositories
- Commits: Conventional Commits (Commitizen)

## API

- Base URL: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Frontend proxies `/api/*` to backend via Vite config
- Custom exceptions: `EntityNotFoundException` (404), `EntityAlreadyExistsException` (409), `ValidationException` (400)

## UI Testing

When smoke-testing UI changes in the browser, **enable Demo Mode first** (toggle in the top-right header). Demo Mode switches the backend to a separate demo database with pre-built sample data, so real financial data is not accidentally modified. Remember to disable it when done.

## Gotchas

- Passwords stored in OS Keyring, never in YAML or code
- SQLite uses `NullPool` and `check_same_thread=False` for FastAPI compatibility
- SQLite stores booleans as `0`/`1` integers — in React JSX, `{0 && <Component />}` renders "0". Always use `!!value &&` or `value > 0 &&` for SQLite boolean fields in JSX conditionals
- Frontend `TransactionsTable.tsx` changes require updating all consumers: `Transactions.tsx` and `TransactionCollapsibleList.tsx`
- Scraping has 5-minute timeout and daily rate limit (one scrape per account per day)
- CORS only allows localhost:5173 by default (configurable via `CORS_ORIGINS` env var)
- Closing an investment auto-creates a balance snapshot of 0 on the last transaction date (not the closure date)
- Investment balance snapshots override transaction-based balance when present (snapshot-first, transaction fallback)
