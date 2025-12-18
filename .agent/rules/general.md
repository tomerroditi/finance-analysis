# Finance Analysis Dashboard - Global Context

## Project Overview
Personal finance tracking and analysis system that automates data collection from Israeli financial institutions (banks, credit cards, insurance) and provides intelligent expense categorization, budgeting, project budget tracking, and investment tracking.

**Tech Stack:**
- **UI:** Streamlit 1.42.2 + streamlit-antd-components
- **Data:** SQLite (via SQLAlchemy 2.0.29) + Pandas 2.2.3
  - **Database Location:** `C:\Users\<username>\.finance-analysis\data.db`
- **Scraping:** Playwright (via israeli-bank-scrapers npm package)
- **Package Manager:** Poetry
- **Python:** 3.12+
- **Testing:** pytest with custom `@pytest.mark.sensitive` for internet-dependent tests

## Architecture Principles

### Layered Architecture (Strict Dependency Flow)
```
Pages (Thin) → Components (UI + Services interaction) → Services (Business Logic) → Repositories (Data Access) → Database
```

**Key Rules:**
- **Pages** are SLIM - they instantiate components and handle page-level layout only
- **Components** contain UI implementation AND interact with services for data/actions
- **Services** orchestrate business logic and call repositories
- **Repositories** handle ALL database operations (Repository Pattern)
- **Utils** contain pure helper functions only

**Example Flow:**
1. Page creates a component instance
2. Component renders UI elements and calls services when user interacts
3. Service processes business logic and calls repositories for data
4. Repository executes database queries and returns DataFrames
5. Component receives data and displays it

### Repository Pattern
All database access goes through repository classes in `fad/app/data_access/`. Each repository:
- Manages one primary table
- Returns pandas DataFrames or primitives
- Uses SQLAlchemy for queries
- Never contains business logic

## Key Business Concepts

### 1. Transaction Amount Convention
- **Negative amounts:** Money SPENT (expenses, outgoing payments)
- **Positive amounts:** Money RECEIVED (income, refunds, deposits)
- Always account for sign when implementing business logic (e.g., filtering expenses, calculating totals)

### 2. Tagging & Categorization
- **Categories:** High-level grouping (e.g., "Food", "Transport", "Savings")
- **Tags:** Sub-categories (e.g., "Groceries", "Restaurants" under "Food")
- **Rule-Based System:** Automatic tagging via `tagging_rules` table with priority-based matching
- **Priority-Based:** Higher priority number = evaluated first, overrides lower priority rules
- **Manual Override:** Users can manually tag individual transactions

### 3. Split Transactions
Single transaction can be split across multiple categories/tags with different amounts. Original transaction remains in main table, individual splits stored in `split_transactions` table.

### 4. Budgets
Two types of budgets:
- **Regular Budgets:** Monthly spending limits per category or tag
- **Project Budgets:** Time-limited budgets for specific projects (e.g., home renovation, wedding planning)
- Tracked in `budget_rules` table
- "Total Budget" is a special category for overall monthly spending limit

### 5. Non-Expense Categories
Categories excluded from expense analysis:
- **Ignore:** Internal account transfers, credit card billing transactions (we scrape itemized card transactions directly, so bank's summary charge is ignored)
- **Salary/Other Income:** Income sources (positive amounts)
- **Savings/Investments:** Money allocated but not spent
- **Liabilities:** Debt/loan payments

### 6. Scraping Sessions
- Daily scraping limits tracked in `scraping_history` table
- 2FA automation via custom `two_fa.py` module
- Israeli financial providers only (see `naming_conventions.py` for full list)

### 7. Investment Tracking
Manual tracking of investment portfolios (stocks, bonds, pension, crypto, real estate, etc.). Daily balance updates for liquid assets. See `InvestmentsType` enum for supported types.

## Code Quality Standards

### What NOT to Do
- ❌ No "change log" comments explaining modifications
- ❌ No obvious comments restating code
- ❌ No TODO comments (create GitHub issues instead)
- ❌ No dead/commented-out code
- ❌ No direct database access outside repositories
- ❌ No business logic in pages or components
- ❌ No Streamlit widgets without unique `key` parameter

### What TO Do
- ✅ Self-documenting code with meaningful names
- ✅ Type hints everywhere
- ✅ NumPy-style docstrings for public methods
- ✅ Minimal, focused functions (single responsibility)
- ✅ Explain WHY in comments, not WHAT
- ✅ **Unique widget keys** for ALL Streamlit widgets
- ✅ Account for transaction sign (negative = expense, positive = income)

### Docstring Example
```python
def calculate_monthly_budget(category: str, year: int, month: int) -> float:
    """
    Calculate total budget for a category in a specific month.
    
    Parameters
    ----------
    category : str
        Budget category name.
    year : int
        Target year.
    month : int
        Target month (1-12).
    
    Returns
    -------
    float
        Total budget amount in ILS.
    """
```

## Security & Credentials

### Credential Storage
- **Passwords:** Stored securely in Windows Keyring (NOT in YAML files)
- **YAML Files:** Store only non-sensitive configuration (usernames, account numbers, provider names)
- **Default Templates:** `fad/resources/default_credentials.yaml`
- **User Credentials:** `credentials.yaml` (created on first run, in `.gitignore`)
- **2FA Codes:** Handled via automated SMS/email interception

### Sensitive Data
- Never log passwords or credentials
- Use `@pytest.mark.sensitive` for tests accessing real accounts
- Keep test credentials separate (`test_credentials.yaml`)

## Adding New Features

### New Financial Provider
1. Add provider name to appropriate list in `naming_conventions.py` (CreditCards/Banks/Insurances enum)
2. Add login fields to `LoginFields.providers_fields` dict
3. Update `fad/scraper/scrapers.py` if israeli-bank-scrapers supports it
4. Add to UI in `my_accounts.py` page

### New Page
1. Create file in `fad/app/pages/`
2. Register in `main.py` navigation using `st.Page()`
3. Use existing components from `fad/app/components/` or create new ones
4. Keep page logic minimal - delegate to components

### New Component
1. Create in `fad/app/components/`
2. Make reusable and focused on single UI concern
3. Component calls services for data/actions
4. Always use unique widget keys (pass prefix parameter if needed)

### New Analysis Feature
1. Add service method in `fad/app/services/`
2. Create/update repository methods if new queries needed
3. Build component in `fad/app/components/` for UI
4. Add plotting utilities in `fad/app/utils/plotting.py` if visualization needed
5. Integrate component into relevant page

### Database Schema Changes
1. Update table enum in `naming_conventions.py` (Tables enum)
2. Update/create repository in `fad/app/data_access/`
3. Update services that use affected tables
4. Consider migration logic for existing user databases

## Testing

### Running Tests
```bash
# All tests except sensitive ones
poetry run pytest -m "not sensitive"

# All tests including sensitive (requires real credentials)
poetry run pytest
```

### Test Guidelines
- Unit tests for services, repositories, utils
- Integration tests for scraping (marked `@pytest.mark.sensitive`)
- Mock external dependencies in unit tests
- Use Faker for test data generation
- Current coverage is low - improvements welcome

## Development Workflow

### Setup
```bash
poetry install
poetry run streamlit run main.py
```

### Commit Conventions
- Using Commitizen for conventional commits
- Automatic changelog generation on version bump
- Semantic versioning via `poetry version`

## Common Patterns

### Streamlit Widget Keys
Always provide unique keys to avoid state conflicts:
```python
# ✅ Good - unique keys prevent conflicts
st.selectbox("Category", options, key=f"cat_selector_{page_id}_{row_id}")
st.button("Save", key=f"save_btn_{transaction_id}")

# ❌ Bad - can cause state conflicts across pages/components
st.selectbox("Category", options)
st.button("Save")
```

### Data Processing
- Use pandas for transformations
- Keep DataFrames immutable where possible
- Return copies from repositories
- Always check transaction sign when filtering/summing

## UI/UX Guidelines
- Follow Streamlit best practices
- Use streamlit-antd-components for enhanced UI
- Maintain consistent layout across pages
- Support wide layout mode (set in `main.py`)
- Provide clear navigation structure
- **Always use unique keys for widgets**

## File Structure
```
finance-analysis/
├── .github/                  # GitHub configs, Copilot instructions
├── fad/                      # Main application package
│   ├── app/                  # Streamlit app
│   │   ├── components/       # Reusable UI components (interact with services)
│   │   ├── data_access/      # Repository pattern (DB access)
│   │   ├── pages/            # Streamlit pages (SLIM - use components)
│   │   ├── services/         # Business logic layer
│   │   ├── utils/            # Helper functions (plotting, widgets, etc.)
│   │   ├── naming_conventions.py  # Central enums & constants
│   │   └── overview.py       # Main dashboard page
│   ├── resources/            # YAML configs (credentials, categories, icons)
│   └── scraper/              # Web scraping for Israeli financial providers
├── tests/                    # pytest test suite
├── main.py                   # Streamlit entry point
└── pyproject.toml            # Poetry dependencies
```

## Future Enhancements (Backlog)
- CSV import for manual transaction upload
- Conflicting tagging rules detector
- Multi-user authentication system
- Shared accounts for families
- Forecasting engine
- PDF payslip parsing
- Enhanced data visualizations

---

**When working on this project:**
1. Respect the layered architecture (Pages → Components → Services → Repositories)
2. Keep pages slim - UI logic goes in components
3. Use repository pattern for ALL database access
4. Keep business logic in services only
5. Always use unique keys for Streamlit widgets
6. Account for transaction sign (negative = expense, positive = income/refund)
7. Store passwords in Windows Keyring, not YAML files
