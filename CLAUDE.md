# Finance Analysis Dashboard

Personal finance tracking system for Israeli financial institutions. FastAPI backend + React 19 frontend.

## Commands

```bash
# Backend
poetry run uvicorn backend.main:app --reload          # Dev server (port 8000)
poetry run pytest                                      # All tests
poetry run pytest tests/backend/unit/                  # Unit tests only
poetry run pytest -k "test_budget"                     # By keyword
poetry run pytest <path> --no-cov                     # Targeted run (repo's 40% coverage gate fails small runs without --no-cov)

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

`npm run backend` auto-bootstraps the Python venv via `.claude/scripts/bootstrap_venv.sh` if `.venv/` is missing — the first backend start in a fresh worktree takes ~90s, subsequent starts are instant. Frontend deps still install manually:

```bash
cd frontend && npm install
```

To bootstrap the backend explicitly (without starting it), run the script directly:

```bash
./.claude/scripts/bootstrap_venv.sh
```

Manual equivalent if you'd rather see each step:

```bash
python3.12 -m venv .venv && source .venv/bin/activate && pip install poetry && poetry install --no-root
```

**Why the auto-bootstrap exists:** Git worktrees only contain source files — they don't inherit the parent's `.venv/`, and a missing venv breaks `npm run backend` with a cryptic `sh: .venv/bin/activate: No such file or directory`. The bootstrap script is idempotent (exits silently when `.venv/bin/uvicorn` already exists), so the hot path stays fast.

To run backend tests in a fresh worktree without the ~90s bootstrap, use the main checkout's venv against the worktree source (from the worktree root): `../../../.venv/bin/python -m pytest <path> --no-cov`

User data lives in `~/.finance-analysis/` (SQLite DB at `data.db`). Auto-created on first run. Credentials and categories live in the DB; passwords are stored in the OS Keyring. Default categories ship bundled in `backend/resources/*.yaml` and are seeded into the DB on first run.

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

## Branch & PR Workflow

- **PRs default to `dev`**, not `main`. Feature branches merge into `dev`.
- `dev` accumulates changes; when ready, `dev` is merged into `main` via a PR that triggers the full CI/CD pipeline (Windows installer build + GitHub release). macOS bundles are no longer built in CI — see `.claude/rules/installation_and_updates.md`.
- Never open a PR directly to `main` for feature work — only `dev → main` merges go there.

## Pre-PR Checklist

Run these locally and get them **all green before opening a PR** — CI runs the same checks and a red PR wastes a round-trip. Run from the repo root unless noted. See `.claude/rules/ci_and_release.md` (CI parity) and `.claude/rules/testing.md` (e2e details).

```bash
# 1. Backend tests (full suite — matches CI's `poetry run pytest`)
poetry run pytest

# 2. Frontend lint + type-check/build + unit tests (matches CI)
cd frontend && npm run lint && npm run build && npm test && cd ..

# 3. Frontend e2e (Playwright) — needs BOTH servers up, so run via the orchestrator
python .claude/scripts/with_server.py -- bash -c \
  "cd frontend && npx playwright test --reporter=line"
```

- **Run the whole suite, not just the one test you touched.** Backend `pytest` has a 40 % coverage gate — a targeted run needs `--no-cov` (see Commands), but the pre-PR run is the full suite with coverage on.
- **e2e is required, not optional** — `npm test` (vitest) and e2e (`playwright test`) are different layers. e2e specs live in `frontend/e2e/` and drive the real UI in Demo Mode; type-checking and unit tests miss the focus-trap / click-outside / query-invalidation bugs UI patches introduce. Every UI patch must add or update an e2e spec (see the CLAUDE.md "UI Testing" section).
- **Sandbox (Claude Code on the web) gotcha:** a bare `npx playwright test` fails because the bundled Chromium lags `package.json`. Point Playwright at the installed full-chrome binary via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` — full procedure in `.claude/rules/testing.md` → "Running e2e specs". **Verified green is the only "verified"** — a browser that failed to launch means the spec did not run.
- **Fresh worktree:** the first backend command auto-bootstraps `.venv/` (~90 s); frontend deps need a manual `cd frontend && npm install`. See "Environment Setup" above.
- Use a Conventional Commits subject on the PR merge (drives the Commitizen version bump).

## API

- Base URL: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Frontend proxies `/api/*` to backend via Vite config
- Custom exceptions: `EntityNotFoundException` (404), `EntityAlreadyExistsException` (409), `ValidationException` (400)

## UI Testing

When smoke-testing UI changes in the browser, **enable Demo Mode first** (toggle in Settings — click Settings in the sidebar). Demo Mode switches the backend to a separate demo database with pre-built sample data, so real financial data is not accidentally modified. Remember to disable it when done.

**REQUIRED for every UI patch (including small ones):** Drive the actual user
flow with the Playwright MCP before marking the fix resolved, and add an e2e
spec under `frontend/e2e/`. Type-checking and reasoning miss the bugs UI
patches usually contain (focus traps, click-outside handlers, keyboard-induced
reposition, query invalidation remounting). Full procedure in
`.claude/rules/testing.md` → "Verifying UI patches with Playwright" (includes
how to run e2e via `with_server.py` and the Claude-Code-on-the-web Chromium
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` override needed when `npx playwright
install` can't fetch a browser).

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

- **`unique_id` is a per-table auto-increment** — bank #5 and credit-card #5 are different transactions. Never key merged/cross-table data by bare `unique_id`; always pair it with the table (`source` / `source_table`). See `.claude/rules/backend_repositories.md` → "unique_id Is Per-Table"
- Passwords stored in OS Keyring, never in YAML or code
- SQLite uses `NullPool` and `check_same_thread=False` for FastAPI compatibility
- SQLite stores booleans as `0`/`1` integers — in React JSX, `{0 && <Component />}` renders "0". Always use `!!value &&` or `value > 0 &&` for SQLite boolean fields in JSX conditionals
- Frontend `TransactionsTable.tsx` changes require updating all consumers: `Transactions.tsx` and `TransactionCollapsibleList.tsx`
- Scraping has 5-minute timeout and daily rate limit (one scrape per account per day)
- CORS only allows localhost:5173 by default (configurable via `CORS_ORIGINS` env var)
- Closing an investment auto-creates a balance snapshot of 0 on the last transaction date (not the closure date)
- Investment balance snapshots override transaction-based balance when present (snapshot-first, transaction fallback)
- Alembic migrations run on startup (`backend/main.py` → `alembic upgrade head`) AFTER `Base.metadata.create_all` — they must be idempotent (fresh DBs already have current-model tables), set `down_revision` to the current head, and use `op.batch_alter_table(..., recreate="always")` to drop SQLite constraints/columns
- Toggling Demo Mode (including e2e specs that flip it) re-copies the frozen demo snapshot — hand-added demo accounts/data are lost (real data is untouched)
