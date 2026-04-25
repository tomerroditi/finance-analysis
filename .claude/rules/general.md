# Finance Analysis Dashboard - Global Context

## Project Overview
Personal finance tracking and analysis system that automates data collection from Israeli financial institutions (banks, credit cards, insurance) and provides intelligent expense categorization, budgeting, project budget tracking, and investment tracking.

**Tech Stack:**
- **Backend:** FastAPI (Python 3.12+) + Uvicorn
- **Frontend:** React 19 + Vite + TypeScript
- **Styling:** Tailwind CSS 4
- **Data:** SQLite (via SQLAlchemy 2.0.29) + Pandas 2.2.3
- **Scraping:** Playwright (via israeli-bank-scrapers npm package)
- **Package Managers:** Poetry (Backend), NPM (Frontend)
- **State Management:** TanStack Query (React Query) + Zustand
- **Testing:** pytest (Backend)

**Important Paths:**
- **Database:** `~/.finance-analysis/data.db`
- **Credentials:** `~/.finance-analysis/credentials.yaml`
- **User Data Dir:** `~/.finance-analysis/`

## Architecture Principles

### Decoupled Architecture
The system consists of a standalone FastAPI backend and a React frontend.

#### Backend Layers (Strict Dependency Flow)
```
Routes (FastAPI) -> Services (Business Logic) -> Repositories (Data Access) -> Database
```

**Key Rules:**
- **Routes** define entry points, handle HTTP concerns, and use Pydantic models for request/response validation.
- **Services** orchestrate business logic and call repositories.
- **Repositories** handle ALL database operations using the Repository Pattern with SQLAlchemy ORM.
- **Models** define DB schemas (SQLAlchemy ORM models in `backend/models/`). Pydantic request/response schemas are defined inline in route files.

**Service Naming Convention:**
- Frontend and API use **plural** service names: `banks`, `credit_cards`, `cash`, `manual_investments`
- These match the `Services` enum values in `backend/constants/providers.py`
- Table names may differ (e.g., `credit_card_transactions` table vs `credit_cards` service)

#### Frontend Layers
```
Pages (Routing) -> Components (UI Logic) -> Services (API Interaction) -> State Hubs (Zustand/Query)
```

**Key Rules:**
- **Pages** are high-level views registered in the router.
- **Components** are reusable UI units. Use atomic design principles.
- **Services/API** centralized axios client in `src/services/api.ts`.

## Key Business Concepts

### 1. Transaction Amount Convention
- **Negative amounts:** Money SPENT (expenses, outgoing payments)
- **Positive amounts:** Money RECEIVED (income, refunds, deposits)
- Always account for sign when implementing business logic (negative = expense).

### 2. Tagging & Categorization
- **Categories:** High-level grouping (e.g., "Food", "Transport").
- **Tags:** Sub-categories (e.g., "Groceries", "Restaurants").
- **Rule-Based System:** Automatic tagging via `tagging_rules` table with priority-based matching.
- **Priority:** Higher priority = evaluated first.

### 3. Split Transactions
Single transaction can be split across multiple categories/tags. Original remains in main table; individual splits in `split_transactions`.

### 4. Budgets
- **Regular Budgets:** Monthly spending limits per category/tag.
- **Project Budgets:** Time-limited budgets for specific projects (e.g., Home Renovation).
- "Total Budget" is a special "category" for overall monthly limit.

### 5. Non-Expense Categories
- **Ignore:** Internal transfers, credit card billing summaries.
- **Income:** Salary, Other Income.
- **Investments:** Allocated funds.
- **Liabilities:** Debt payments.

### 6. Investment Balance Snapshots
- **Balance snapshots** store timestamped market-value observations per investment (`investment_balance_snapshots` table).
- **Resolution:** Snapshot-first, transaction-based fallback (`-(sum of all transactions)`).
- **Sources:** `manual` (user-entered), `calculated` (fixed-rate daily compounding), `scraped` (future).
- **Closing:** Auto-creates a 0-balance snapshot on the last transaction date. Close date is user-selectable and editable after closing.
- **Fixed-rate:** Daily compounding with protected dates (manual/scraped snapshots never overwritten).

## Code Quality Standards

### What NOT to Do
- No business logic in Routes or Frontend Components.
- No direct DB access outside Repositories.
- No obvious comments or dead code.
- No verbose comments explaining code that is already self-explanatory.
- No raw Axios calls inside components (use `src/services/api.ts`).

### What TO Do
- Type hints in Python; strict TypeScript in Frontend.
- NumPy-style docstrings for Python; JSDoc for complex React hooks/functions.
- Functional React components with hooks.
- Pydantic models for all API request/response bodies.
- Account for transaction sign (negative = expense).

## Security & Credentials
- **Passwords:** Stored in OS Keyring (never in code/config).
- **Sensitive Data:** Never log credentials. Use 2FA automation for scraping.

## Adding New Features

### New API Route
1. Define route in `backend/routes/`.
2. Implement logic in a Service class.
3. Access data via Repository.
4. Add endpoint to `frontend/src/services/api.ts`.
5. Or use `python .claude/scripts/scaffold_feature.py <name>` to generate boilerplate.
6. **PWA cache layer:** decide whether the response is sensitive (credentials), real-time (scraping/polling), or normal. Update SW + persister exclusion lists accordingly. See `.claude/rules/frontend_pwa.md`.

### New UI Page/Component
1. Create in `frontend/src/pages/` or `frontend/src/components/`.
2. Use Tailwind CSS 4 for styling.
3. Use TanStack Query for data fetching.

## Error Handling
- Define custom exceptions in `backend/errors.py` (inherit from `AppException`): `EntityNotFoundException` (404), `EntityAlreadyExistsException` (409), `ValidationException` (400), `BadRequestException` (400).
- Register global handlers in `backend/main.py`.
- Raise exceptions in repositories/services — routes stay clean (no try/except for domain errors).

## Testing
- **Backend:** `poetry run pytest`. Use markers like `@pytest.mark.sensitive`.
- **Test structure:** `tests/backend/unit/` (unit tests), `tests/backend/routes/` (endpoint tests), `tests/backend/integration/` (pipeline tests).
- **Frontend:** (Planned) Vitest for unit tests.

## Development Workflow
1. **Backend:** `poetry run uvicorn backend.main:app --reload`
2. **Frontend:** `npm run dev` (Vite)
3. **Commits:** Conventional Commits (Commitizen).

## Environment Setup (New Clone / Worktree)
1. `python3.12 -m venv .venv && source .venv/bin/activate && pip install poetry && poetry install --no-root`
2. `cd frontend && npm install`
3. Worktrees auto-configure unique ports based on directory name to avoid conflicts.

## File Structure
```
finance-analysis/
├── backend/            # FastAPI application
│   ├── constants/      # Enums & constants (tables, providers, categories, budget)
│   ├── routes/         # API endpoints (includes inline Pydantic schemas)
│   ├── services/       # Business logic
│   ├── repositories/   # DB access (Repository Pattern)
│   ├── models/         # SQLAlchemy ORM models
│   ├── scraper/        # Web scraping module (israeli-bank-scrapers integration)
│   ├── resources/      # YAML config files (default categories, icons)
│   ├── utils/          # Utility functions
│   └── database.py     # DB connection session
├── frontend/           # React application
│   ├── src/
│   │   ├── components/ # Reusable UI components
│   │   ├── pages/      # View components
│   │   ├── services/   # API client (api.ts)
│   │   ├── hooks/      # Custom React hooks
│   │   ├── stores/     # Zustand state stores
│   │   ├── utils/      # Utility functions
│   │   └── context/    # React Context providers
│   └── public/
├── tests/              # Test suite
│   └── backend/
│       ├── unit/       # Unit tests (models, repos, services, utils)
│       ├── routes/     # Endpoint/integration tests
│       └── integration/# Pipeline tests
├── fad/                # DEPRECATED: Legacy code / Original Streamlit package (ignore)
└── .claude/            # Agent rules and scripts
```
