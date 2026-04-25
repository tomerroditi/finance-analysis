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

# Scraper
python -m scraper --list                               # List all providers
python -m scraper <provider> --show-browser             # Run scraper with visible browser
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
- **Scraper:** `scraper/` — Pure-Python scraper framework (Playwright + httpx), replaces Node.js
- **Frontend:** `frontend/src/` — React 19, Vite, TanStack Query, Zustand, Tailwind CSS 4
- **Tests:** `tests/backend/unit/` — pytest with test classes, docstrings required
- **Rules:** `.claude/rules/` — detailed architecture docs covering services, repos, scraper, frontend (i18n, responsive, PWA/offline cache), testing
- **Data Flow:** `frontend/src/components/dataflow/dataFlowData.ts` — comprehensive map of all features and how data flows through the system (sources → ingestion → processing → storage → management → analytics → frontend). Read this for a quick overview of the entire application.

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

When smoke-testing UI changes in the browser, **enable Demo Mode first** (toggle in Settings — click Settings in the sidebar). Demo Mode switches the backend to a separate demo database with pre-built sample data, so real financial data is not accidentally modified. Remember to disable it when done.

## Scraper Framework

The `scraper/` package at the project root is a pure-Python scraper framework using Playwright and httpx, replacing the old Node.js integration. It provides:

- **18 provider scrapers** (11 banks + 7 credit cards) in `scraper/providers/`
- **Base classes:** `BrowserScraper` (Playwright lifecycle + login), `ApiScraper` (API-via-browser)
- **Backend integration:** `backend/scraper/adapter.py` bridges async scrapers to the sync pipeline
- **Demo mode:** Automatically redirects to dummy scrapers that generate fake data
- **Adding a new provider:** Create a class in `scraper/providers/banks/` or `credit_cards/`, register in `scraper/models/credentials.py` PROVIDER_CONFIGS, and export in the `__init__.py`
- **Import caveat:** `backend/scraper/` and root `scraper/` share a name. Backend code uses `_import_scraper_module()` helper (in `adapter.py`) to resolve root package. Test dirs use `test_scraper/` prefix to avoid pytest collision.

## PWA / Offline Cache

The frontend ships as a PWA — service worker precaches the build, persists the React Query cache to IndexedDB, and shows toasts for SW lifecycle events.

- **Service worker:** `frontend/src/sw.ts` (custom, `injectManifest` mode). Runtime-caches `/api` GETs (NetworkFirst, 4 s timeout); excludes `/api/credentials/*`, `/api/scraping/*`, `/api/backups`.
- **Query persistence:** `frontend/src/queryClient.ts` — `idb-keyval` async persister + global `MutationCache.onSuccess` debounced invalidator (200 ms). Bump `PERSIST_BUSTER` when API response shapes change.
- **When adding endpoints:** decide if the response is sensitive / real-time / normal and update both the SW URL filter AND the persister `shouldDehydrateQuery` rule. Never one without the other.
- **Detailed rules:** `.claude/rules/frontend_pwa.md`

## Internationalization (Hebrew/English)

- **Bilingual UI:** Full Hebrew + English support via `i18next` / `react-i18next`
- **RTL:** Automatic direction switching. Use Tailwind CSS 4 logical properties (`ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start`, etc.) instead of physical `left`/`right`
- **All user-visible strings** must use `t("section.key")` — no hardcoded text. Add keys to both `en.json` and `he.json`
- **Numbers in RTL:** Wrap with `dir="ltr"` inside translated text
- **Detailed rules:** `.claude/rules/frontend_i18n.md`

## Gotchas

- Passwords stored in OS Keyring, never in YAML or code
- SQLite uses `NullPool` and `check_same_thread=False` for FastAPI compatibility
- SQLite stores booleans as `0`/`1` integers — in React JSX, `{0 && <Component />}` renders "0". Always use `!!value &&` or `value > 0 &&` for SQLite boolean fields in JSX conditionals
- Frontend `TransactionsTable.tsx` changes require updating all consumers: `Transactions.tsx` and `TransactionCollapsibleList.tsx`
- Scraping has 5-minute timeout and daily rate limit (one scrape per account per day)
- CORS only allows localhost:5173 by default (configurable via `CORS_ORIGINS` env var)
- Closing an investment auto-creates a balance snapshot of 0 on the last transaction date (not the closure date)
- Investment balance snapshots override transaction-based balance when present (snapshot-first, transaction fallback)
