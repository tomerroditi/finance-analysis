---
trigger: always_on
---

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

## Architecture Principles

### Decoupled Architecture
The system consists of a standalone FastAPI backend and a React frontend.

#### Backend Layers (Strict Dependency Flow)
```
Routes (FastAPI) → Services (Business Logic) → Repositories (Data Access) → Database
```

**Key Rules:**
- **Routes** define entry points, handle HTTP concerns, and use Pydantic models for request/response validation.
- **Services** orchestrate business logic and call repositories.
- **Repositories** handle ALL database operations using the Repository Pattern with SQLAlchemy ORM.
- **Models** define DB schemas (SQLAlchemy ORM models in `backend/models/`) and Pydantic validation schemas.

**Service Naming Convention:**
- Frontend and API use **plural** service names: `banks`, `credit_cards`, `cash`, `manual_investments`
- These match the `Services` enum values in `backend/naming_conventions.py`
- Table names may differ (e.g., `credit_card_transactions` table vs `credit_cards` service)

#### Frontend Layers
```
Pages (Routing) → Components (UI Logic) → Services (API Interaction) → State Hubs (Zustand/Query)
```

**Key Rules:**
- **Pages** are high-level views registered in the router.
- **Components** are reusable UI units. Use atomic design principles.
- **Services/API** centralized axios client in `src/services/api.ts`.

## Agent Context & Workflow Management

### 1. Instruction Synchronization
- **Rule:** Global context and instruction files (under `.agent/rules/` and `.agent/instructions/`) MUST be updated concurrently when changing their related code or architecture.
- **Purpose:** Ensure the agent's "brain" and project rules always reflect the actual state of the codebase.

### 2. Workflow Automation
- **Rule:** Common, repetitive, or complex useful sequences of actions should be saved as workflow files in `.agent/workflows/`.
- **Format:** Use the YAML frontmatter + Markdown format as described in the system instructions.
- **Purpose:** Standardize procedures for deployment, testing, or feature creation.

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
- **Savings/Investments:** Allocated funds.
- **Liabilities:** Debt payments.

## Code Quality Standards

### What NOT to Do
- ❌ No business logic in Routes or Frontend Components.
- ❌ No direct DB access outside Repositories.
- ❌ No obvious comments or dead code.
- ❌ No raw Axios calls inside components (use `src/services/api.ts`).

### What TO Do
- ✅ Type hints in Python; strict TypeScript in Frontend.
- ✅ NumPy-style docstrings for Python; JSDoc for complex React hooks/functions.
- ✅ Functional React components with hooks.
- ✅ Pydantic models for all API request/response bodies.
- ✅ Account for transaction sign (negative = expense).

## Security & Credentials
- **Passwords:** Stored in OS Keyring (never in code/config).
- **Sensitive Data:** Never log credentials. Use 2FA automation for scraping.

## Adding New Features

### New API Route
1. Define route in `backend/routes/`.
2. Implement logic in a Service class.
3. Access data via Repository.
4. Add endpoint to `frontend/src/services/api.ts`.

### New UI Page/Component
1. Create in `frontend/src/pages/` or `frontend/src/components/`.
2. Use Tailwind CSS 4 for styling.
3. Use TanStack Query for data fetching.

## Testing
- **Backend:** `poetry run pytest`. Use markers like `@pytest.mark.sensitive`.
- **Frontend:** (Planned) Vitest for unit tests.

## File Structure
```
finance-analysis/
├── backend/            # FastAPI application
│   ├── routes/         # API endpoints
│   ├── services/       # Business logic
│   ├── repositories/   # DB access (Repository Pattern)
│   ├── models/         # Pydantic & SQLAlchemy models
│   └── database.py     # DB connection session
├── frontend/           # React application
│   ├── src/
│   │   ├── components/ # Reusable UI components
│   │   ├── pages/      # View components
│   │   ├── services/   # API client (api.ts)
│   │   └── hooks/      # Custom React hooks
│   └── public/
├── fad/                # Legacy code / Original Streamlit package
└── .agent/             # Agent rules and workflows
```

## Development Workflow
1. **Backend:** `poetry run uvicorn backend.main:app --reload`
2. **Frontend:** `npm run dev` (Vite)
3. **Commits:** Conventional Commits (Commitizen).
