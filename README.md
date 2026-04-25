# Finance Analysis

Personal finance dashboard for Israeli households. Scrapes bank, credit-card,
and insurance/pension data, classifies transactions, and surfaces budgets,
projects, investments, and retirement projections in a single bilingual
(Hebrew/English) UI.

> Detailed architecture and conventions live in [`CLAUDE.md`](./CLAUDE.md) and
> the `.claude/rules/` directory. This README is the quick-start.

## Stack

- **Backend** — FastAPI (Python 3.12) + SQLAlchemy 2 + SQLite + Pandas
- **Scraper** — pure-Python framework (Playwright + httpx) under `scraper/`
- **Frontend** — React 19 + Vite + TypeScript + Tailwind CSS 4
- **State** — TanStack Query (server data) + Zustand (UI state)
- **Tests** — `pytest` (backend), `vitest` + `@testing-library/react` (frontend),
  Playwright (e2e)
- **Packaging** — Poetry for Python, npm for frontend; NSIS / DMG installers
  built by `release.yml`

## Quick start

```bash
# 1) Backend deps
python3.12 -m venv .venv && source .venv/bin/activate
pip install poetry && poetry install --no-root

# 2) Frontend deps
cd frontend && npm install && cd ..

# 3) Run both servers
poetry run uvicorn backend.main:app --reload       # http://localhost:8000
cd frontend && npm run dev                          # http://localhost:5173
```

The first run creates `~/.finance-analysis/` (SQLite DB, credentials YAML,
categories YAML). Passwords are stored in the OS keychain — never in YAML or
code.

API docs at http://localhost:8000/docs (disabled in production).

## Common commands

```bash
# Backend
poetry run pytest                                  # full test suite
poetry run pytest tests/backend/unit               # just unit tests
poetry run pytest -k "test_budget"                 # by keyword

# Frontend (from frontend/)
npm run dev                                        # dev server
npm run build                                      # tsc -b && vite build
npm run lint                                       # ESLint
npm test                                           # vitest run
npm run test:e2e                                   # Playwright

# Both servers (one shell)
python .claude/scripts/with_server.py -- <command>

# Scaffold a new feature (route + service + repo)
python .claude/scripts/scaffold_feature.py <name>

# Run a scraper provider in isolation
python -m scraper --list
python -m scraper <provider> --show-browser
```

## Demo mode

The header has a Demo Mode toggle. It swaps the active SQLite DB for a
pre-built fixture (the "Cohen family" — see the `demo-data-generation`
skill) so you can poke at every screen without touching real data.
**Disable Demo Mode before scraping or editing real records.**

## Architecture in one paragraph

```
Routes (FastAPI)
  -> Services (business logic)
  -> Repositories (only layer with DB / file access)
  -> SQLite + YAML
```

Routes are thin: they parse Pydantic models, call services, and translate
domain exceptions to HTTP status codes. Services own all calculations,
deduplication, and validation. Repositories are the only place that touches
SQLAlchemy or YAML. See `.claude/rules/backend_*.md` for the detailed rules.

The frontend mirrors that split: pages compose feature components, components
fetch data through hooks (TanStack Query) and shared utils, and `services/api.ts`
is the single axios client. See `.claude/rules/frontend_*.md`.

## Goals & roadmap

- [x] Automated scraping for Israeli banks, credit cards, and insurance/pension
- [x] Rule-based auto-tagging with priority + JSON conditions
- [x] Monthly + project budgets with refunds and split-transaction support
- [x] Investments with manual/calculated/scraped balance snapshots
- [x] Liabilities with auto-generated payment schedules
- [x] Retirement / FIRE calculator
- [x] Bilingual UI (Hebrew + English) with full RTL support
- [ ] See [`docs/next-features.md`](./docs/next-features.md) for the planned
      next big rocks (forecasting, CSV import, mobile-first refresh, …).

## Contributing

- Conventional Commits via Commitizen — `cz commit` is your friend.
- Open a PR; `.github/workflows/ci.yml` runs backend tests + frontend lint,
  build, and vitest. PRs must be green before merge.
- Read the relevant `.claude/rules/*.md` file before changing a layer for the
  first time. The rules encode hard-won conventions that aren't obvious from
  the code alone.
